// Presentation helpers operate only on saved, independently validated records.
export const BENCHMARK_METHODS=['qaoa','milp','structured_random'];
export const BENCHMARK_NAMES={qaoa:'QAOA · ideal Aer',milp:'Native MILP · HiGHS',structured_random:'Structured random'};
export function benchmarkMedian(values){const a=values.toSorted((x,y)=>x-y);return a.length?(a[Math.floor(a.length/2)]+a[Math.floor((a.length-1)/2)])/2:null;}
export function benchmarkSummary(runs){return Object.fromEntries(BENCHMARK_METHODS.map(method=>{
 const rows=runs.filter(r=>r.method===method),valid=rows.filter(r=>r.valid_answer),fractions=rows.filter(r=>r.status!=='error'&&r.feasible_sample_fraction!==null);
 return [method,{runs:rows.length,valid_answers:valid.length,optimal_answers:rows.filter(r=>r.hit_optimum).length,errors:rows.filter(r=>r.status==='error').length,
 median_average_minutes:benchmarkMedian(valid.map(r=>r.best_average_flow_minutes)),median_relative_gap:benchmarkMedian(valid.map(r=>r.relative_optimality_gap)),
 median_total_seconds:benchmarkMedian(rows.map(r=>r.timings.total_seconds)),median_cpu_seconds:benchmarkMedian(rows.map(r=>r.timings.total_cpu_seconds)),
 median_feasible_sample_fraction:benchmarkMedian(fractions.map(r=>r.feasible_sample_fraction))}];
}));}
export function quantumRule(data,name){
 const P=data.penalty;
 if(name==='one')return {name:'One plan per car',qubits:data.groups.A,pairs:data.groups.A.flatMap((i,k)=>data.groups.A.slice(k+1).map(j=>[i,j])),coefficient:P/2,
 formula:`${P}(x₀ + x₁ + x₂ + x₃ − 1)²`,ising:`${2*P}I − ${P}(Z₀ + Z₁ + Z₂ + Z₃) + ${P/2}∑ᵢ<ⱼ ZᵢZⱼ`,
 detail:'Car A has four candidate plans. The full square penalizes both a missing car and multiple selections. It contributes to four RZ and six RZZ gates in each layer.'};
 const gun=name==='gun',pair=gun?[0,6]:[2,7],i=pair[0],j=pair[1];
 return {name:gun?'Gun conflict':'Shared power limit',qubits:pair,pairs:[pair],coefficient:P/4,
 formula:`${P}x${i}x${j}`,ising:`${P/4}(I − Z${i} − Z${j} + Z${i}Z${j})`,
 detail:gun?'x₀ and x₆ put A and B on gun 1 during the first slot. This pair is forbidden even though its total power is 50 kW.':'x₂ draws 50 kW and x₇ draws 25 kW in the first slot, on different guns of the same 50 kW module. Their 75 kW total is forbidden.'};
}
export function ruleTouchesGate(rule,operation){return operation.name==='rz'?rule.qubits.includes(operation.qubits[0]):operation.name==='rzz'&&rule.pairs.some(pair=>pair.every(q=>operation.qubits.includes(q)));}
