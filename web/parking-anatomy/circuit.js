const circuitEscape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let circuitView = {weight:null, zoom:1, svg:'', python:''};
function circuitPython(record) {
  return `"""Actual two-layer EV QAOA circuit exported from Qiskit ${FIXTURE.quantum.qiskit_version}.
Waiting weight: ${record.weight}; safe penalty: ${record.penalty}.
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
circuit = QuantumCircuit(5, name='EV_QAOA')
circuit.h(range(5))
for layer in range(2):
    for qubit, coefficient in enumerate(z):
        if coefficient:
            circuit.rz(2 * gamma[layer] * coefficient / scale, qubit)
    for i, j, coefficient in zz:
        if coefficient:
            circuit.rzz(2 * gamma[layer] * coefficient / scale, i, j)
    for qubit in range(5):
        circuit.rx(2 * beta[layer], qubit)
circuit.measure_all()
print(circuit.draw(output='text', fold=110))
# Optional high-resolution export:
# circuit.draw(output='mpl', fold=18).savefig('ev-qaoa.svg')
`;
}
function makeCircuitSvg(fixture, record) {
  const rowHeight=68, left=205, top=84, cell=76, next=Array(5).fill(0), placed=[];
  for (const operation of record.operations) {
    if(operation.name==='barrier')continue;
    const lo=Math.min(...operation.qubits),hi=Math.max(...operation.qubits);
    const occupied=Array.from({length:hi-lo+1},(_,i)=>lo+i);
    const column=Math.max(...occupied.map(q=>next[q]));
    for(const q of occupied)next[q]=column+1;
    placed.push({...operation,column});
  }
  const width=left+Math.max(...next)*cell+45,height=top+4*rowHeight+72;
  const lines=fixture.options.map((b,i)=>`<text x="14" y="${top+i*rowHeight-9}" fill="var(--circuit-text,#f4f4f4)" font-size="13">q${i} / x${i} · Car ${circuitEscape(b.vehicle_id)}</text><text x="14" y="${top+i*rowHeight+10}" fill="var(--circuit-muted,#c6c6c6)" font-size="11">${circuitEscape(b.station_id)} / ${circuitEscape(b.slot_id)}</text><line x1="${left-20}" x2="${width-20}" y1="${top+i*rowHeight}" y2="${top+i*rowHeight}" stroke="var(--circuit-wire,#6f6f6f)"/>`).join('');
  const gates=placed.map((op,index)=>{
    const x=left+op.column*cell,ys=op.qubits.map(q=>top+q*rowHeight);
    const category=op.name==='h'?'prepare':op.name==='rx'?'mix':op.name==='measure'?'measure':'cost';
    const color={prepare:'#78a9ff',cost:'#be95ff',mix:'#42be65',measure:'#f1c21b'}[category];
    const label=op.name==='measure'?'M':op.name.toUpperCase();
    const message=`${label} · ${op.qubits.map(q=>'q'+q).join(' ↔ ')}${op.parameters.length?' · angle '+op.parameters.join(', '):''}${op.name==='measure'?' → classical bit '+op.clbits[0]:''}`;
    const body=(ys.length>1?`<line x1="${x}" x2="${x}" y1="${Math.min(...ys)}" y2="${Math.max(...ys)}" stroke="${color}" stroke-width="2"/>`:'')+ys.map(y=>`<rect x="${x-25}" y="${y-18}" width="50" height="36" fill="var(--circuit-gate,#262626)" stroke="${color}" stroke-width="1.5"/><text x="${x}" y="${y+4}" text-anchor="middle" fill="var(--circuit-text,#f4f4f4)" font-size="12">${label}</text>`).join('');
    return `<g class="circuit-gate" role="button" tabindex="0" data-gate-description="${circuitEscape(message)}" aria-label="${circuitEscape(message)}"><title>${circuitEscape(message)}</title>${body}</g>`;
  }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" id="actual-qiskit-circuit" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="group" aria-labelledby="circuit-svg-title circuit-svg-desc" style="font-family:'IBM Plex Mono',monospace"><title id="circuit-svg-title">Actual five-qubit, two-layer Qiskit QAOA circuit</title><desc id="circuit-svg-desc">Generated from the repository QuantumCircuit. H prepares each qubit, RZ and coupled RZZ encode cost, RX mixes, and M measures. Gate angles are parameterized by beta and gamma. Select a gate for its angle.</desc><text x="14" y="26" fill="var(--circuit-text,#f4f4f4)" font-size="15">EV QAOA · 2 layers · 4 adjustable angles</text><text x="14" y="47" fill="var(--circuit-muted,#c6c6c6)" font-size="11">H: prepare · RZ/RZZ: cost · RX: mix · M: measure</text>${lines}${gates}</svg>`;
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
