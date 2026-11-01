const eqNumber = n => Number(n.toFixed(6)).toString();
const eqN = n => `<mn>${eqNumber(n)}</mn>`;
const eqX = i => `<msub><mi>x</mi><mn>${i}</mn></msub>`;
const eqZ = i => `<msub><mi>Z</mi><mn>${i}</mn></msub>`;
const eqMath = content => `<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mrow>${content}</mrow></math>`;
function eqPolynomial(terms){return terms.filter(([c])=>Math.abs(c)>1e-10).map(([c,v],i)=>`${i?`<mo>${c<0?'−':'+'}</mo>`:c<0?'<mo>−</mo>':''}${eqN(Math.abs(c))}${v}`).join('');}
function renderEquations(fixture,weight){
 const host=document.getElementById('equation-cost');if(!host)return;
 renderGateConstraints(fixture,weight);
 const r=fixture.quantum.records[Math.round(weight*100)],o=optionsAt(fixture,weight),p=r.penalty;
 document.getElementById('equation-setting').textContent=`Current waiting weight λ = ${weight.toFixed(2)} · penalty P = ${eqNumber(p)} · coefficients follow the controls above`;
 const cost=eqPolynomial(o.map((b,i)=>[b.score,eqX(i)]));
 host.innerHTML=eqMath('<mi>C</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo>'+cost);
 const sumA=[0,1,2,3].map(eqX).join('<mo>+</mo>');
 const squared=s=>`<msup><mrow><mo>(</mo>${s}<mo>−</mo><mn>1</mn><mo>)</mo></mrow><mn>2</mn></msup>`;
 document.getElementById('equation-qubo').innerHTML=eqMath(`<mi>F</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mi>C</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>+</mo>${eqN(p)}<mo>[</mo>${squared(sumA)}<mo>+</mo>${squared(eqX(4))}<mo>+</mo>${eqX(0)}${eqX(4)}<mo>]</mo>`);
 const linear=eqPolynomial([[2*p,''],...o.map((b,i)=>[b.score-p,eqX(i)])]);
 const pairs=eqPolynomial(r.zz.map(([i,j,c])=>[4*c,eqX(i)+eqX(j)]));
 document.getElementById('equation-expanded').innerHTML=eqMath('<mi>F</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo>'+linear)+eqMath('<mo>+</mo>'+pairs);
 const z=eqPolynomial([[r.offset,'<mi>I</mi>'],...r.z.map((c,i)=>[c,eqZ(i)])]);
 document.getElementById('equation-ising').innerHTML=eqMath('<msub><mi>H</mi><mi>C</mi></msub><mo>=</mo>'+z)+eqMath('<mo>+</mo>'+eqPolynomial(r.zz.map(([i,j,c])=>[c,eqZ(i)+eqZ(j)])));
 document.getElementById('equation-normalized').innerHTML=eqMath(`<msub><mover><mi>H</mi><mo>~</mo></mover><mi>C</mi></msub><mo>=</mo><mfrac><mrow><msub><mi>H</mi><mi>C</mi></msub><mo>−</mo>${eqN(r.offset)}<mi>I</mi></mrow>${eqN(r.scale)}</mfrac>`);
 document.getElementById('equation-bookings').innerHTML=o.map((b,i)=>`<tr><th scope="row">x<sub>${i}</sub></th><td>Car ${b.vehicle_id} · ${b.station_id} · ${b.slot_id==='early'?'08:00–09:00':'09:00–10:00'}</td><td>${b.score.toFixed(2)}</td></tr>`).join('');
 const best=scheduleAt(fixture,weight).best,bits=fixture.options.map((_,i)=>best.bookings.some(b=>b.index===i)?1:0).join('');
 document.getElementById('equation-answer').textContent=`At this preference, ${bits} in booking order is the minimum-cost valid plan, with score ${best.score.toFixed(2)} points and zero constraint penalty.`;
}

function renderGateConstraints(fixture,weight){
 const host=document.getElementById('gate-constraint-rows');if(!host)return;
 const r=fixture.quantum.records[Math.round(weight*100)];
 const row=(gate,why,term)=>`<tr><th scope="row">${gate}</th><td>${why}</td><td>${term}</td></tr>`;
 let html=row('H · q₀–q₄','Prepares all 32 booking patterns in superposition. No scheduling constraint is enforced here.','Preparation');
 for(let i=0;i<5;i++)html+=row(`RZ · q${i}`,circuitConstraint({name:'rz',qubits:[i]}),`${eqNumber(r.z[i])} Z${i}; angle = ${eqNumber(2*r.z[i]/r.scale)} γₖ`);
 for(const [i,j,c] of r.zz)html+=row(`RZZ · q${i} ↔ q${j}`,circuitConstraint({name:'rzz',qubits:[i,j]}),`${eqNumber(c)} Z${i}Z${j}; angle = ${eqNumber(2*c/r.scale)} γₖ`);
 html+=row('RX · q₀–q₄','Mixes amplitudes to explore new booking patterns. It is a search operation, not a feasibility constraint.','Mixer Σ Xᵢ; angle = 2βₖ');
 html+=row('M · q₀–q₄','Reads candidate bits. Reverse Qiskit’s displayed count order to obtain x₀…x₄, then validate the schedule.','Measurement / classical validation');
 host.innerHTML=html;
}
