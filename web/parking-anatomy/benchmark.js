let selectedRule='one';
function renderQuantumRule(name='one'){
 selectedRule=name;const data=FIXTURE.shared_power,rule=quantumRule(data,name);
 document.querySelectorAll('[data-quantum-rule]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.quantumRule===name)));
 document.getElementById('rule-name').textContent=rule.name;
 document.getElementById('rule-formula').textContent=rule.formula;
 document.getElementById('rule-ising').textContent=rule.ising;
 document.getElementById('rule-detail').textContent=rule.detail;
 const operations=data.quantum.operations,related=operations.filter(op=>ruleTouchesGate(rule,op));
 document.getElementById('rule-gates').innerHTML=related.slice(0,related.length/2).map(op=>`<span>${op.name.toUpperCase()} · ${op.qubits.map(q=>'q'+q).join(' ↔ ')}</span>`).join('');
 document.getElementById('rule-gate-count').textContent=`${related.length} highlighted cost gates across two layers. RZ angles combine this rule with other costs and penalties. The identity term adds no gate.`;
 document.querySelectorAll('#shared-circuit-svg .circuit-gate').forEach(g=>{
  g.classList.toggle('rule-highlight',ruleTouchesGate(rule,operations[Number(g.dataset.sourceIndex)]));
  g.classList.toggle('rule-dim',!ruleTouchesGate(rule,operations[Number(g.dataset.sourceIndex)]));
 });
}
function benchmarkNumber(value,digits=1){return value===null?'—':Number(value).toFixed(digits);}
function benchmarkPercent(value){return value===null?'—':(100*value).toFixed(1)+'%';}
function renderBenchmark(id='original'){
 const report=FIXTURE.benchmark,record=report.cases.find(c=>c.id===id);if(!record)throw Error('Unknown benchmark case');
 document.getElementById('benchmark-case').value=id;
 const s=record.scenario;
 document.getElementById('benchmark-inputs').textContent=`${record.qubits} plan bits · ${s.modules.length} × 50 kW module${s.modules.length===1?'':'s'} · ${s.num_slots} × ${s.slot_minutes}-minute slot${s.num_slots===1?'':'s'} · exact optimum ${record.reference.average_flow_minutes} min average arrival → completion`;
 document.getElementById('benchmark-cars').textContent=s.vehicles.map(v=>`${v.id}: ${v.required_energy_kwh} kWh, up to ${v.max_power_kw} kW, arrival ${v.arrival_minute}, deadline ${v.deadline_minute}`).join(' · ');
 const summary=benchmarkSummary(record.runs);
 document.getElementById('benchmark-rows').innerHTML=BENCHMARK_METHODS.map(method=>{const r=summary[method];return `<tr><th scope="row">${BENCHMARK_NAMES[method]}</th><td>${benchmarkNumber(r.median_average_minutes)} min</td><td>${benchmarkPercent(r.median_relative_gap)}</td><td>${r.valid_answers}/${r.runs}</td><td>${r.optimal_answers}/${r.runs}</td><td>${method==='milp'?'N/A · solver':benchmarkPercent(r.median_feasible_sample_fraction)}</td><td>${benchmarkNumber(r.median_cpu_seconds*1000,2)} ms</td><td>${benchmarkNumber(r.median_total_seconds*1000,2)} ms</td><td>${r.errors}</td></tr>`;}).join('');
 const q=summary.qaoa,m=summary.milp,r=summary.structured_random;
 const faster=m.median_total_seconds<q.median_total_seconds;
 document.getElementById('benchmark-verdict').textContent=`QAOA found the exact optimum in ${q.optimal_answers}/${q.runs} runs; MILP in ${m.optimal_answers}/${m.runs}; structured random in ${r.optimal_answers}/${r.runs}. ${faster?'MILP had lower median elapsed runtime than the Aer workflow.':'The table reports the measured runtime comparison.'} These small cases demonstrate no quantum speedup.`;
 const a=record.analytical_reference;
 document.getElementById('benchmark-uniform').textContent=`Analytical reference only: ${a.feasible_choices} valid schedules / ${a.encoded_bitstrings.toLocaleString()} unrestricted bitstrings = ${benchmarkPercent(a.uniform_bitstring_feasibility)} feasibility. Uniformly choosing one plan per car instead gives ${a.feasible_choices}/${a.one_plan_per_car_choices} = ${benchmarkPercent(a.structured_uniform_feasibility)}. Neither number is a measured optimizer run.`;
 document.getElementById('benchmark-provenance').textContent=`Saved ${report.generated_at_utc.slice(0,10)} UTC · Python ${report.environment.python} · Qiskit ${report.environment.qiskit} · Aer ${report.environment.qiskit_aer} · SciPy ${report.environment.scipy} · ${report.environment.os}/${report.environment.architecture} · report v${report.schema_version}. Source hashes and all records are in the download.`;
 document.getElementById('benchmark-failures').textContent=record.runs.filter(r=>!r.hit_optimum).map(r=>`${BENCHMARK_NAMES[r.method]}, seed ${r.seed}: ${r.error?.message||(r.valid_answer?'valid answer, '+r.best_average_flow_minutes+' min average; missed optimum':'No physically valid sample')}`).join('; ')||'Every run returned a valid optimum in this case.';
}
function initQuantumBenchmarks(){
 const report=FIXTURE.benchmark;if(!report)throw Error('Missing benchmark evidence');
 document.getElementById('benchmark-case').innerHTML=report.cases.map(c=>`<option value="${c.id}">${c.label}</option>`).join('');
 document.getElementById('benchmark-case').addEventListener('change',e=>renderBenchmark(e.target.value));
 document.querySelectorAll('[data-quantum-rule]').forEach(b=>b.addEventListener('click',()=>renderQuantumRule(b.dataset.quantumRule)));
 document.getElementById('inspect-rule-circuit').addEventListener('click',()=>{setQuantumModel('shared');document.querySelector('.shared-circuit-details').open=true;navigateDemo('#shared-circuit-meta');});
 document.getElementById('benchmark-download').addEventListener('click',()=>circuitDownload(JSON.stringify(report,null,2),'ev-quantum-benchmark-v1.json','application/json'));
 document.getElementById('shared-download-highlight').addEventListener('click',()=>{const svg=document.getElementById('shared-qiskit-circuit').outerHTML.replaceAll('var(--circuit-text,#f4f4f4)','#161616').replaceAll('var(--circuit-muted,#c6c6c6)','#525252').replaceAll('var(--circuit-wire,#6f6f6f)','#8d8d8d').replaceAll('var(--circuit-gate,#262626)','#ffffff').replace('<title','<style>.rule-highlight{filter:drop-shadow(0 0 3px #a56eff)}.rule-highlight rect:not([fill="transparent"]),.rule-highlight line{stroke:#8a3ffc;stroke-width:4}.rule-dim{opacity:.25}</style><title');circuitDownload(svg,'ev-'+selectedRule+'-rule.svg','image/svg+xml');});
 renderQuantumRule();renderBenchmark();
}
initQuantumBenchmarks();
