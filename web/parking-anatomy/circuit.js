function circuitConstraint(op,fixture){
 const q=op.qubits;
 if(fixture?.model_kind==='shared_power') {
  if(op.name==='h')return 'Prepare this charging-plan qubit in superposition; no physical rule is enforced by H.';
  if(op.name==='rx')return 'Explore alternative plan selections. The X mixer can produce invalid assignments.';
  if(op.name==='measure')return 'Read one plan bit, then check energy, exactly one plan per car, gun occupancy and shared module power.';
  if(op.name==='rz')return 'Arrival-to-completion cost and single-Z contributions from the exactly-one and conflict penalties.';
  if(op.name==='rzz')return fixture.options[q[0]].vehicle_id===fixture.options[q[1]].vehicle_id
   ?'Part of the exactly-one-plan penalty for this car. Its single-Z and constant contributions complete the rule.'
   :'Part of a physical conflict penalty: these two plans overlap on one gun or exceed the shared module limit. Single-Z and constant terms complete the penalty.';
 }
 if(op.name==='h')return 'Preparation only: creates superposition on this booking qubit; it does not encode a constraint.';
 if(op.name==='rx')return 'Mixer only: explores alternative booking patterns. It does not enforce feasibility; invalid candidates remain possible.';
 if(op.name==='measure')return 'Readout only: converts this qubit into a booking bit. The decoded sample must still be checked for one booking per car and charger conflicts.';
 if(op.name==='rzz')return q.includes(4)?'Shared charger constraint: x0 and x4 both request North at 08:00. This ZZ interaction is part of P x0 x4; the matching single-Z and constant terms complete that penalty.':'Car A exactly-one constraint: this pair belongs to (x0+x1+x2+x3−1)². The ZZ interaction discourages selecting two A bookings together; single-Z and constant terms also encode the full rule.';
 if(op.name==='rz')return 'Single-booking cost plus constraint contributions: '+(q[0]===0?'A/North/early score, Car A exactly-one rule, and the North/early conflict with Car B.':q[0]===4?'B/North/early score, Car B exactly-one rule, and the North/early conflict with Car A.':'this Car A booking score and Car A exactly-one rule.')+' An RZ gate is not one isolated rule: its coefficient combines every single-Z contribution after the QUBO-to-Ising substitution.';
 return '';
}
const circuitEscape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let circuitView = {weight:null, zoom:1, svg:'', python:''};
function circuitPython(record,settings={}) {
  const qubits=settings.qubits||5;
  return `"""Actual two-layer EV QAOA circuit exported from Qiskit ${FIXTURE.quantum.qiskit_version}.
${settings.description||`Waiting weight: ${record.weight}; safe penalty: ${record.penalty}.`}
This constructs the parameterized circuit; it does not train or run it.
Install dependencies: pip install qiskit matplotlib pylatexenc
"""
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector

z = ${JSON.stringify(record.z)}
zz = ${JSON.stringify(record.zz)}
scale = ${record.scale}
gamma = ParameterVector('gamma', 2)
beta = ParameterVector('beta', 2)
circuit = QuantumCircuit(${qubits}, name='EV_QAOA')
circuit.h(range(${qubits}))
for layer in range(2):
    for qubit, coefficient in enumerate(z):
        if coefficient:
            circuit.rz(2 * gamma[layer] * coefficient / scale, qubit)
    for i, j, coefficient in zz:
        if coefficient:
            circuit.rzz(2 * gamma[layer] * coefficient / scale, i, j)
    for qubit in range(${qubits}):
        circuit.rx(2 * beta[layer], qubit)
circuit.measure_all()
print(circuit.draw(output='text', fold=110))
# Optional high-resolution export:
# circuit.draw(output='mpl', fold=18).savefig('ev-qaoa.svg')
`;
}
function layoutCircuit(record){
 const qubits=record.num_qubits||Math.max(...record.operations.flatMap(op=>op.qubits))+1;
 const next=Array(qubits).fill(0),placed=[],stages=[];let current='';
 for(const [sourceIndex,operation] of record.operations.entries()){
  if(operation.name==='barrier'){const fence=Math.max(...next)+1;next.fill(fence);continue;}
  const layer=(operation.parameters.join(' ').match(/\[(\d+)\]/)||[])[1];
  const stage=operation.name==='h'?'Prepare':operation.name==='measure'?'Measure':`Layer ${Number(layer)+1} · ${operation.name==='rx'?'mix β':'cost γ'}${layer}`;
  if(stage!==current){next.fill(Math.max(...next)+(current?1:0));current=stage;stages.push({title:stage,start:Math.max(...next),end:Math.max(...next)});}
  const lo=Math.min(...operation.qubits),hi=Math.max(...operation.qubits),occupied=Array.from({length:hi-lo+1},(_,i)=>lo+i),column=Math.max(...occupied.map(q=>next[q]));
  for(const q of occupied)next[q]=column+1;
  stages.at(-1).end=Math.max(stages.at(-1).end,column);
  placed.push({...operation,column,stage,sourceIndex});
 }
 return {placed,stages,next};
}
function circuitAngleLabel(op){
 if(!op.parameters.length)return '';
 const expression=op.parameters[0],match=expression.match(/(gamma|beta)\[(\d+)\]/);
 if(!match)return expression;
 const numeric=expression.replace(/(gamma|beta)\[\d+\]/,'1');
 const factors=numeric.replace(/[()]/g,'').split('*').map(Number),coefficient=factors.reduce((a,b)=>a*b,1);
 return `${Number(coefficient.toFixed(3))}${match[1]==='gamma'?'γ':'β'}${match[2]}`;
}
function makeCircuitSvg(fixture, record,svgId='actual-qiskit-circuit') {
  const rowHeight=92, left=205, top=118, cell=110;
  const {placed,stages,next}=layoutCircuit(record);
  const width=left+Math.max(...next)*cell+45,height=top+(fixture.options.length-1)*rowHeight+100;
  const lines=fixture.options.map((b,i)=>`<text x="14" y="${top+i*rowHeight-9}" fill="var(--circuit-text,#f4f4f4)" font-size="13">q${i} / x${i} · Car ${circuitEscape(b.vehicle_id)}</text><text x="14" y="${top+i*rowHeight+10}" fill="var(--circuit-muted,#c6c6c6)" font-size="11">${circuitEscape(b.station_id)} / ${circuitEscape(b.slot_id)}</text><line x1="${left-20}" x2="${width-20}" y1="${top+i*rowHeight}" y2="${top+i*rowHeight}" stroke="var(--circuit-wire,#6f6f6f)"/>`).join('');
  const gates=placed.map((op,index)=>{
    const x=left+op.column*cell,ys=op.qubits.map(q=>top+q*rowHeight);
    const category=op.name==='h'?'prepare':op.name==='rx'?'mix':op.name==='measure'?'measure':'cost';
    const color={prepare:'#78a9ff',cost:'#be95ff',mix:'#42be65',measure:'#f1c21b'}[category];
    const label=op.name==='measure'?'M':op.name.toUpperCase();
    const message=`${label} · ${op.qubits.map(q=>'q'+q).join(' ↔ ')}${op.parameters.length?' · angle '+op.parameters.join(', '):''}${op.name==='measure'?' → classical bit '+op.clbits[0]:''} · ${circuitConstraint(op,fixture)}`;
    const angle=circuitEscape(circuitAngleLabel(op));
    const body=op.name==='rzz'?`<line x1="${x}" x2="${x}" y1="${Math.min(...ys)}" y2="${Math.max(...ys)}" stroke="${color}" stroke-width="2"/>${ys.map(y=>`<rect x="${x-4}" y="${y-4}" width="8" height="8" fill="${color}"/>`).join('')}<text x="${x+9}" y="${(ys[0]+ys[1])/2-5}" fill="var(--circuit-text,#f4f4f4)" font-size="12">ZZ</text><text x="${x+9}" y="${(ys[0]+ys[1])/2+12}" fill="var(--circuit-muted,#c6c6c6)" font-size="10">${angle}</text>`:ys.map(y=>`<rect x="${x-25}" y="${y-18}" width="50" height="36" fill="var(--circuit-gate,#262626)" stroke="${color}" stroke-width="1.5"/><text x="${x}" y="${y+4}" text-anchor="middle" fill="var(--circuit-text,#f4f4f4)" font-size="12">${label}</text><text x="${x}" y="${y+34}" text-anchor="middle" fill="var(--circuit-muted,#c6c6c6)" font-size="10">${op.name==='measure'?'c'+op.clbits[0]:angle}</text>`).join('');
    const hitArea=`<rect x="${x-28}" y="${Math.min(...ys)-24}" width="100" height="${Math.max(...ys)-Math.min(...ys)+62}" fill="transparent" stroke="none" pointer-events="all"/>`;
    return `<g class="circuit-gate" data-operation="${op.name}" data-qubits="${op.qubits.join(',')}" data-source-index="${op.sourceIndex}" role="button" tabindex="0" data-gate-description="${circuitEscape(message)}" aria-label="${circuitEscape(message)}"><title>${circuitEscape(message)}</title>${hitArea}${body}</g>`;
  }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" id="${svgId}" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="group" aria-labelledby="${svgId}-title ${svgId}-desc" style="font-family:'IBM Plex Mono',monospace"><title id="${svgId}-title">Actual ${fixture.options.length}-qubit, two-layer Qiskit QAOA circuit</title><desc id="${svgId}-desc">Generated from the repository QuantumCircuit. H prepares each qubit, RZ and coupled RZZ encode cost, RX mixes, and M measures. Gate angles are parameterized by beta and gamma. Select a gate for its angle.</desc><text x="14" y="26" fill="var(--circuit-text,#f4f4f4)" font-size="15">EV QAOA · 2 layers · 4 adjustable angles</text><text x="14" y="47" fill="var(--circuit-muted,#c6c6c6)" font-size="11">H: prepare · RZ/RZZ: cost · RX: mix · M: measure</text>${stages.map(st=>`<text x="${left+st.start*cell-26}" y="78" fill="var(--circuit-text,#f4f4f4)" font-size="12">${circuitEscape(st.title)}</text><line x1="${left+st.start*cell-42}" x2="${left+st.start*cell-42}" y1="91" y2="${height-30}" stroke="var(--circuit-wire,#6f6f6f)" stroke-dasharray="3 5"/>`).join('')}${lines}${gates}</svg>`;
}
function circuitDownload(text,name,type){const link=document.createElement('a');const url=URL.createObjectURL(new Blob([text],{type}));link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function renderCircuit(fixture,weight){
  const host=document.getElementById('circuit-svg');if(!host)return;
  const record=fixture.quantum?.records?.[Math.round(weight*100)];
  if(!record)throw new Error('Missing actual Qiskit circuit for selected waiting weight');
  if(circuitView.weight===record.weight)return;
  circuitView.weight=record.weight;circuitView.svg=makeCircuitSvg(fixture,record);circuitView.python=circuitPython(record);
  host.innerHTML=circuitView.svg;
  const meta=document.getElementById('circuit-meta');if(meta)meta.textContent=`Qiskit ${fixture.quantum.qiskit_version} · 5 qubits · 2 layers · 14 RZZ gates · waiting weight ${weight.toFixed(2)} · penalty ${record.penalty.toFixed(2)}`;
  const code=document.getElementById('circuit-code');if(code)code.textContent=circuitView.python;
  const description=document.getElementById('circuit-description');if(description)description.textContent='Select or focus a gate to inspect its real Qiskit parameters. RZZ connects two booking qubits; it is not an independent single-qubit operation.';
  const svg=host.querySelector('svg');svg.style.maxWidth='none';svg.style.width=(Number(svg.getAttribute('width'))*circuitView.zoom)+'px';svg.style.height='auto';
}
function initCircuitControls(){
 const host=document.getElementById('circuit-svg');if(!host)return;
 const describe=event=>{const gate=event.target.closest('[data-gate-description]');if(gate){const out=document.getElementById('circuit-description');if(out)out.textContent=gate.dataset.gateDescription;}};
 host.addEventListener('click',describe);host.addEventListener('focusin',describe);host.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();describe(event);}});
 const zoom=factor=>{circuitView.zoom=Math.min(2,Math.max(.1,factor));const svg=host.querySelector('svg');if(svg){svg.style.width=(Number(svg.getAttribute('width'))*circuitView.zoom)+'px';svg.style.height='auto';}};
 for(const [id,handler] of [['circuit-zoom-in',()=>zoom(circuitView.zoom+.25)],['circuit-zoom-out',()=>zoom(circuitView.zoom-.25)],['circuit-fit',()=>{const svg=host.querySelector('svg');if(svg)zoom(Math.min(1,host.clientWidth/Number(svg.getAttribute('width'))));}],['download-svg',()=>{const svg=circuitView.svg.replaceAll('var(--circuit-text,#f4f4f4)','#161616').replaceAll('var(--circuit-muted,#c6c6c6)','#525252').replaceAll('var(--circuit-wire,#6f6f6f)','#8d8d8d').replaceAll('var(--circuit-gate,#262626)','#ffffff');circuitDownload(svg,'ev-qaoa.svg','image/svg+xml');}],['download-python',()=>circuitDownload(circuitView.python,'ev_qaoa.py','text/x-python')],['copy-python',async()=>{const button=document.getElementById('copy-python');try{await navigator.clipboard.writeText(circuitView.python);button.textContent='Copied';}catch{button.textContent='Use Download Python';}}]]){document.getElementById(id)?.addEventListener('click',handler);}
}
initCircuitControls();
