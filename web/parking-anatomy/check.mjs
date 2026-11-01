import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {Script,runInNewContext} from 'node:vm';
import {scheduleAt,energyOf,encodedStates,safePenalty} from './model.mjs';

const here=dirname(fileURLToPath(import.meta.url));
const fixture=JSON.parse(readFileSync(join(here,'fixture.json'),'utf8'));
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
const encoded=bookings=>fixture.options.map((o,i)=>bookings.some(b=>b.index===i)?'1':'0').join('');
const original=scheduleAt(fixture,.25);
assert.equal(encoded(original.best.bookings),'01001');
close(original.best.cost,fixture.baseline.total_electricity_cost_rupees);
close(original.best.score,fixture.baseline.total_score);
assert.equal(original.best.waiting,fixture.baseline.total_waiting_minutes);
assert.equal(original.candidates.length,4);
assert.equal(original.candidates.filter(c=>c.valid).length,3);
const shorter=scheduleAt(fixture,1);
assert.equal(encoded(shorter.best.bookings),'00101');
close(shorter.best.cost,51.4);assert.equal(shorter.best.waiting,5);close(shorter.best.score,56.4);
for(const weight of [...Array.from({length:101},(_,i)=>i/100),(33-10.4)/65]){
  const model=scheduleAt(fixture,weight),states=encodedStates(model.options);
  assert.equal(states.length,32);assert.equal(states.filter(s=>s.feasible).length,3);
  close(Math.min(...states.map(s=>s.energy)),model.best.score);
  close(energyOf(encoded(model.best.bookings),model.options).penalty,0);
}
assert.equal(encoded(scheduleAt(fixture,(33-10.4)/65).best.bookings),'01001');
close(safePenalty(original.options),57.65);
close(energyOf('00000',original.options).energy,115.30);
close(energyOf('10001',original.options).penalty,57.65);
close(energyOf('10001',original.options).energy,99.35);
assert.equal(fixture.quantum.records.length,101);
for (const [tick,record] of fixture.quantum.records.entries()) {
  const options=scheduleAt(fixture,tick/100).options;
  close(record.weight,tick/100);close(record.penalty,safePenalty(options));
  assert.deepEqual(record.gate_counts,{h:5,rz:10,rzz:14,rx:10,barrier:1,measure:5});
  assert.equal(record.operations.filter(op=>op.name==='rzz').length,14);
  assert.deepEqual(record.parameter_order,['beta[0]','beta[1]','gamma[0]','gamma[1]']);
  for(const state of encodedStates(options)) {
    close(state.energy,record.energies[parseInt(state.bits,2)]);
    const z=[...state.bits].map(bit=>1-2*Number(bit));
    const diagonal=record.offset+record.z.reduce((sum,c,i)=>sum+c*z[i],0)+record.zz.reduce((sum,[i,j,c])=>sum+c*z[i]*z[j],0);
    close(state.energy,diagonal);
  }
}

for(const name of ['index.html','index-light.html']){
  const html=readFileSync(join(here,'dist',name),'utf8');
  const source=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(source,'Built script exists');new Script(source,{filename:name});
  assert.equal(html.includes('<!--SCRIPT-->'),false);
}
console.log('Passed: Python baseline, alternate preference, tie order, 102 QUBO comparisons, 3232 Python/QUBO/Ising energy comparisons, real Qiskit gate records, and emitted JavaScript syntax.');

const viewer=runInNewContext(readFileSync(join(here,'circuit.js'),'utf8')+';({layoutCircuit,makeCircuitSvg})',{document:{getElementById:()=>null}});
for(const record of fixture.quantum.records){
 const {placed,stages}=viewer.layoutCircuit(record);
 assert.equal(placed.length,44);assert.equal(stages.length,6);
 for(let i=1;i<stages.length;i++)assert.ok(stages[i].start>stages[i-1].end,'Stage boundaries must be preserved');
 const wireColumns=Array(5).fill(-1);
 for(const op of placed){for(const q of op.qubits){assert.ok(op.column>wireColumns[q]);wireColumns[q]=op.column;}}
 const svg=viewer.makeCircuitSvg(fixture,record);
 assert.equal((svg.match(/data-operation="rzz"/g)||[]).length,14);
 assert.equal((svg.match(/data-source-index=/g)||[]).length,44);
 assert.equal((svg.match(/>ZZ<\/text>/g)||[]).length,14,'One shared label per two-qubit gate');
}
console.log('Passed: all 101 circuit layouts preserve six stages, per-wire order, measurements and one symbol per RZZ gate.');
