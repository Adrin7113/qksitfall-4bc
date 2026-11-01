import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import {sharedEnergy} from './shared-model.mjs';
const here=dirname(fileURLToPath(import.meta.url));
const fixture=JSON.parse(readFileSync(join(here,'fixture.json'),'utf8')),data=fixture.shared_power;
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
assert.equal(data.plans.length,8);assert.equal(data.states.length,256);
assert.equal(data.states.filter(s=>s.valid).length,4);
assert.equal(data.penalty,121);assert.equal(data.constant,242);
for(const expected of data.states){
 const actual=sharedEnergy(data,expected.bits);
 assert.equal(actual.valid,expected.valid,expected.bits);
 close(actual.objective,expected.objective);close(actual.penalty,expected.penalty);close(actual.energy,expected.energy);
 const z=[...expected.bits].map(bit=>1-2*Number(bit));
 const ising=data.quantum.offset+data.quantum.z.reduce((sum,c,i)=>sum+c*z[i],0)+data.quantum.zz.reduce((sum,[i,j,c])=>sum+c*z[i]*z[j],0);
 close(ising,actual.energy);
}
for(const [name,expected] of Object.entries({optimal:[true,90,45],delayed:[true,120,60],overload:[false,211,null],gun:[false,211,null]})){
 const actual=sharedEnergy(data,data.presets[name]);assert.equal(actual.valid,expected[0]);close(actual.energy,expected[1]);assert.equal(actual.average,expected[2]);
}
close(sharedEnergy(data,'00000000').energy,242);
const saved=sharedEnergy(data,data.saved_run.bits.join(''));
assert.equal(saved.valid,true);close(saved.objective,data.saved_run.total_flow_minutes);
close(data.saved_run.valid_sample_fraction,data.saved_run.valid_shots/data.saved_run.shots);
assert.ok(data.saved_run.valid_shots>0&&data.saved_run.valid_shots<=data.saved_run.shots);
assert.equal(data.quantum.num_qubits,8);
const viewer=runInNewContext(readFileSync(join(here,'circuit.js'),'utf8')+';({layoutCircuit,makeCircuitSvg,circuitPython})',{document:{getElementById:()=>null},FIXTURE:fixture});
const adapter={model_kind:'shared_power',options:data.plans.map(p=>({...p,station_id:`${p.module_id}/gun${p.gun}`,slot_id:p.power_kw_by_slot.join(',')}))};
const layout=viewer.layoutCircuit(data.quantum);
assert.equal(layout.next.length,8);assert.equal(layout.stages.length,6);
assert.equal(layout.placed.length,96);assert.equal(data.quantum.gate_counts.rzz,48);
const columns=Array(8).fill(-1);
for(const op of layout.placed)for(const q of op.qubits){assert.ok(op.column>columns[q]);columns[q]=op.column;}
const svg=viewer.makeCircuitSvg(adapter,data.quantum,'shared-qiskit-circuit');
assert.ok(svg.includes('id="shared-qiskit-circuit"'));assert.ok(svg.includes('Actual 8-qubit'));
assert.equal((svg.match(/data-operation="rzz"/g)||[]).length,48);
assert.ok(!svg.includes('North'));assert.ok(!svg.includes('Car A exactly-one constraint'));
const python=viewer.circuitPython(data.quantum,{qubits:8,description:'Shared-power test'});
assert.ok(python.includes('QuantumCircuit(8'));assert.ok(python.includes('range(8)'));
for(const name of ['index.html','index-light.html']){
 const html=readFileSync(join(here,'dist',name),'utf8');
 for(const id of ['architecture','shared-power','lot','algorithm-audit','shared-plan-title','shared-show-sample'])assert.ok(html.includes(`id="${id}"`));
 const chapters=['lot','shared-power','quantum','results'].map(id=>html.indexOf(`<section id="${id}"`));
 assert.ok(chapters.every((position,i)=>position>=0&&(!i||position>chapters[i-1])),'Demo chapters must appear in numerical order.');
 assert.ok(html.includes('id="quantum-shared" role="tabpanel" aria-labelledby="model-tab-shared" hidden'));
 assert.ok(html.indexOf('id="technical-appendix"')>chapters[3],'Audit appendix follows the main demo.');
 assert.ok(html.includes('The current examples do not exchange these offers yet.'));
 assert.ok(html.includes('These results demonstrate no quantum advantage.'));
}
console.log('Passed: 256 Python/browser/Ising shared-power energies, independent physical checks, four presets, saved Aer sample, and actual eight-qubit circuit layout.');
