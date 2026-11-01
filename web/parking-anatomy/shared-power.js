let sharedBits=FIXTURE.shared_power.presets.delayed;
let sharedSelection='delayed';
function renderSharedPower() {
 const data=FIXTURE.shared_power,chosen=sharedEnergy(data,sharedBits);
 const get=id=>document.getElementById(id),escape=circuitEscape;
 const titles={optimal:'Serve B, then release its power.',delayed:'A starts at full power; B waits.',overload:'Two valid car limits can overload a module.',gun:'Enough power still needs two separate guns.',sample:'A plan actually sampled by QAOA.',custom:'Inspect your selected plan bits.'};
 get('shared-plan-title').textContent=titles[sharedSelection];
 get('shared-source').textContent=sharedSelection==='sample'?'Source: best feasible string measured in the saved local Aer run.':sharedSelection==='optimal'?'Source: separate exact classical reference on this grid.':'Source: an illustrative selection from the same Python-generated plans.';
 for(const button of document.querySelectorAll('[data-shared-preset]'))button.setAttribute('aria-pressed',String(button.dataset.sharedPreset===sharedSelection));
 get('shared-status').textContent=chosen.valid?'Valid · one plan per car, separate guns when needed, and no shared-power overload.':chosen.reasons.join(' ');
 get('shared-status').classList.toggle('invalid',!chosen.valid);
 get('shared-average').innerHTML=chosen.valid?`${chosen.average.toFixed(0)} <small>min</small>`:'—';
 get('shared-finish').innerHTML=chosen.valid?`${Math.max(...chosen.plans.map(p=>p.completion_minute))} <small>min</small>`:'—';
 get('shared-objective').innerHTML=`${chosen.objective.toFixed(0)} <small>min</small>`;
 get('shared-penalty').textContent=chosen.penalty.toFixed(0);
 get('shared-energy').textContent=chosen.energy.toFixed(0);
 get('shared-bit-string').innerHTML=[...sharedBits].map(bit=>`<span data-on="${bit==='1'}">${bit}</span>`).join('');
 get('shared-delivery').innerHTML=chosen.plans.length?chosen.plans.map(plan=>`<tr><td>${escape(plan.vehicle_id)} / gun ${plan.gun+1}</td><td>${plan.power_kw_by_slot.join(' → ')} kW</td><td>${plan.charging_energy_kwh} kWh</td><td>${plan.completion_minute} min</td></tr>`).join(''):'<tr><td colspan="4">No charging plans selected.</td></tr>';
 get('shared-power-chart').innerHTML=Array.from({length:data.scenario.num_slots},(_,t)=>{
  const total=chosen.plans.reduce((sum,p)=>sum+p.power_kw_by_slot[t],0);
  const axis=Math.max(75,total),limit=50/axis*100;
  const segments=chosen.plans.map(plan=>`<span class="power-segment power-${plan.vehicle_id.toLowerCase()}" style="width:${plan.power_kw_by_slot[t]/axis*100}%" title="Car ${escape(plan.vehicle_id)}: ${plan.power_kw_by_slot[t]} kW"></span>`).join('');
  return `<div class="power-slot${total>50?' overloaded':''}" role="img" aria-label="Minutes ${t*30} to ${(t+1)*30}: selected plans request ${total} kW of a 50 kW module limit"><div class="power-slot-heading"><span>${t*30}–${(t+1)*30} min</span><strong>${total} / 50 kW</strong></div><div class="power-track">${segments}<span class="power-limit" style="left:${limit}%"></span></div><div class="power-scale"><span>0</span><span style="left:${limit}%">50 kW limit</span><span>${axis}</span></div></div>`;
 }).join('');
 get('shared-plan-bits').innerHTML=data.plans.map((plan,i)=>`<button data-shared-bit="${i}" id="shared-plan-${i}" aria-pressed="${sharedBits[i]==='1'}" aria-label="x${i}: Car ${escape(plan.vehicle_id)}, gun ${plan.gun+1}, ${plan.power_kw_by_slot.join(' then ')} kilowatts, cost ${plan.score} minutes"><span class="mono">x${i}</span><span>Car ${escape(plan.vehicle_id)} · gun ${plan.gun+1}<small>${plan.power_kw_by_slot.join(' → ')} kW · finishes ${plan.completion_minute} min</small></span><strong>${sharedBits[i]}</strong></button>`).join('');
}
function initSharedPower() {
 const data=FIXTURE.shared_power,get=id=>document.getElementById(id);
 get('shared-valid-count').textContent=data.states.filter(s=>s.valid).length;
 get('shared-coefficients').textContent=`Constant: ${data.constant}\nLinear L: [${data.linear.join(', ')}]\n\nQuadratic Q (each pair once):\n`+data.quadratic.map(([i,j,c])=>`x${i} x${j}: ${c}`).join('\n');
 const run=data.saved_run;
 get('shared-run-summary').textContent=run.status==='feasible'?`${run.valid_shots} of ${run.shots} measurements were valid (${(run.valid_sample_fraction*100).toFixed(1)}%). The best feasible sample has ${run.total_flow_minutes} minutes of total arrival-to-completion time, averaging ${run.average_flow_minutes} minutes per car.`:'No feasible sample was measured in this saved run. This does not prove infeasibility.';
 get('shared-show-sample').disabled=run.status!=='feasible';
 const adapter={model_kind:'shared_power',options:data.plans.map(p=>({...p,station_id:`${p.module_id} / gun ${p.gun+1}`,slot_id:`${p.power_kw_by_slot.join(' → ')} kW`}))};
 get('shared-circuit-svg').innerHTML=makeCircuitSvg(adapter,data.quantum,'shared-qiskit-circuit');
 get('shared-circuit-meta').textContent=`8 qubits · 2 layers · ${data.quantum.gate_counts.rzz} RZZ gates · penalty ${data.penalty} · all 256 basis energies checked against the QUBO`;
 const describe=event=>{const gate=event.target.closest('[data-gate-description]');if(gate)get('shared-gate-description').textContent=gate.dataset.gateDescription;};
 get('shared-circuit-svg').addEventListener('click',describe);
 get('shared-circuit-svg').addEventListener('focusin',describe);
 get('shared-circuit-svg').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();describe(event);}});
 document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.sharedPreset){sharedSelection=button.dataset.sharedPreset;sharedBits=data.presets[sharedSelection];renderSharedPower();}
  if(button.dataset.sharedBit!==undefined){const i=Number(button.dataset.sharedBit);sharedBits=[...sharedBits].map((bit,j)=>i===j?(bit==='1'?'0':'1'):bit).join('');sharedSelection='custom';renderSharedPower();get(`shared-plan-${i}`).focus({preventScroll:true});}
  if(button.id==='shared-show-sample'&&run.status==='feasible'){sharedBits=run.bits.join('');sharedSelection='sample';renderSharedPower();}
  if(button.id==='shared-download')circuitDownload(JSON.stringify(data,null,2),'shared-power-qubo.json','application/json');
  if(button.id==='shared-download-python')circuitDownload(circuitPython(data.quantum,{qubits:8,description:`Shared-power module: 8 plan bits; safe penalty ${data.penalty}.`}), 'shared_power_qaoa.py','text/x-python');
 });
 renderSharedPower();
}
initSharedPower();
