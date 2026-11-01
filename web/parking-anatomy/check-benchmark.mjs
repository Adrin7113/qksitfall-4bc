import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {runInNewContext} from 'node:vm';
import {benchmarkSummary,BENCHMARK_METHODS,quantumRule,ruleTouchesGate} from './benchmark-model.mjs';
const fixture=JSON.parse(readFileSync(new URL('fixture.json',import.meta.url))),report=JSON.parse(readFileSync(new URL('benchmark.json',import.meta.url)));
assert.deepEqual(fixture.benchmark,report);assert.equal(report.schema_version,1);
assert.deepEqual(report.config.seeds,[0,1,2,3,4,5,6,7,8,9]);
assert.deepEqual(report.config.qaoa,{layers:2,iterations:80,restarts:2,shots:2048});
const root=process.env.PARKING_SOURCE_ROOT;
for(const [name,hash] of Object.entries(report.source_hashes)){
 assert.equal(hash,fixture.source_hashes[name]);
 if(root)assert.equal(createHash('sha256').update(readFileSync(root+'/'+name)).digest('hex'),hash,`Stale benchmark: ${name}`);
}
for(const [i,c] of report.cases.entries()){
 assert.equal(c.qubits,[8,6,6,12,8][i]);assert.equal(c.runs.length,30);
 assert.equal(c.reference.total_flow_minutes,[90,90,90,120,60][i]);
 assert.deepEqual(benchmarkSummary(c.runs),c.summary);
 for(const method of BENCHMARK_METHODS)assert.deepEqual(c.runs.filter(r=>r.method===method).map(r=>r.seed).toSorted((a,b)=>a-b),report.config.seeds);
 assert.equal(c.summary.milp.median_feasible_sample_fraction,null);
}
const onlyErrors=BENCHMARK_METHODS.map(method=>({method,status:'error',valid_answer:false,hit_optimum:false,feasible_sample_fraction:null,timings:{total_seconds:1,total_cpu_seconds:1}}));
for(const r of Object.values(benchmarkSummary(onlyErrors))){assert.equal(r.median_average_minutes,null);assert.equal(r.median_feasible_sample_fraction,null);assert.equal(r.errors,1);}
for(const r of Object.values(benchmarkSummary([]))){assert.equal(r.runs,0);assert.equal(r.median_total_seconds,null);}
const data=fixture.shared_power;
for(const [name,count] of [['one',20],['power',6],['gun',6]]){
 const rule=quantumRule(data,name),ops=data.quantum.operations.filter(op=>ruleTouchesGate(rule,op));
 assert.equal(ops.length,count);assert.ok(ops.every(op=>['rz','rzz'].includes(op.name)));
 for(const [i,j] of rule.pairs){assert.ok(data.quadratic.some(([a,b,c])=>a===i&&b===j&&c>0));assert.equal(ops.filter(op=>op.name==='rzz'&&op.qubits.includes(i)&&op.qubits.includes(j)).length,2);}
}
// Exercise the UI with a minimal DOM, using actual report records.
const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',value:'',addEventListener(){}});return elements.get(id);};
const api=runInNewContext(readFileSync('benchmark-model.mjs','utf8').replaceAll('export ','')+'\n'+readFileSync('benchmark.js','utf8')+'\n;({renderBenchmark,renderQuantumRule})',{
 FIXTURE:fixture,document:{getElementById:get,querySelectorAll:()=>[]},setQuantumModel(){},navigateDemo(){},circuitDownload(){}});
for(const c of report.cases){api.renderBenchmark(c.id);assert.ok(get('benchmark-rows').innerHTML.includes(`${c.summary.qaoa.optimal_answers}/10`));assert.ok(get('benchmark-verdict').textContent.includes('no quantum speedup'));}
for(const name of ['one','power','gun'])api.renderQuantumRule(name);
for(const file of ['dist/index.html','dist/index-light.html']){
 const html=readFileSync(file,'utf8');assert.ok(html.includes('it is not a quantum speedup'));assert.ok(html.includes('What quantum contributes'.toUpperCase()));
 for(const id of ['benchmark-case','benchmark-download','inspect-rule-circuit'])assert.equal((html.match(new RegExp(`id="${id}"`,'g'))||[]).length,1);
}
console.log('Benchmark checks passed: 150 raw workflows, displayed aggregates, missing/error answers, sampler-only metrics, rule gate membership and source freshness.');
