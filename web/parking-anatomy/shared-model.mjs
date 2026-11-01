// Evaluate the Python-exported model. No quantum computation runs in the browser.
export function sharedEnergy(fixture, bits) {
  if(!/^[01]{8}$/.test(bits))throw new Error('Expected eight plan bits in x0 to x7 order.');
  const selected=[...bits].map(Number),plans=fixture.plans.filter((_,i)=>selected[i]);
  const objective=plans.reduce((sum,p)=>sum+p.score,0);
  const energy=fixture.constant+fixture.linear.reduce((sum,c,i)=>sum+c*selected[i],0)
    +fixture.quadratic.reduce((sum,[i,j,c])=>sum+c*selected[i]*selected[j],0);
  // Physical checks are independent of the QUBO's precomputed conflict edges.
  const reasons=[];
  for(const [id,indices] of Object.entries(fixture.groups)) {
    if(indices.reduce((sum,i)=>sum+selected[i],0)!==1)reasons.push(`Car ${id} needs exactly one plan.`);
  }
  const occupied=new Set(),power=new Map();
  for(const plan of plans) {
    const vehicle=fixture.scenario.vehicles.find(v=>v.id===plan.vehicle_id);
    const delivered=plan.power_kw_by_slot.reduce((sum,p)=>sum+p,0)*fixture.scenario.slot_minutes/60;
    if(Math.abs(delivered-vehicle.required_energy_kwh)>1e-8)reasons.push(`Car ${vehicle.id} has incorrect delivered energy.`);
    if(plan.power_kw_by_slot.some(p=>p<0||p>vehicle.max_power_kw+1e-8))reasons.push(`Car ${vehicle.id} exceeds its power limit.`);
    if(plan.start_minute<vehicle.arrival_minute||plan.completion_minute>vehicle.deadline_minute)reasons.push(`Car ${vehicle.id} misses its time window.`);
    for(let t=plan.start_slot;t<plan.end_slot;t++) {
      const key=`${plan.module_id}/${plan.gun}/${t}`;
      if(occupied.has(key))reasons.push(`Gun ${plan.gun+1} is double-booked in slot ${t+1}.`);
      occupied.add(key);
    }
    plan.power_kw_by_slot.forEach((p,t)=>{const key=`${plan.module_id}/${t}`;power.set(key,(power.get(key)||0)+p);});
  }
  for(const module of fixture.scenario.modules)for(let t=0;t<fixture.scenario.num_slots;t++) {
    const total=power.get(`${module.id}/${t}`)||0;
    if(total>module.power_kw+1e-8)reasons.push(`Slot ${t+1} requests ${total} kW; the module limit is ${module.power_kw} kW.`);
  }
  return {bits,plans,objective,energy,penalty:energy-objective,valid:reasons.length===0,reasons,
    average:reasons.length===0?objective/fixture.scenario.vehicles.length:null};
}
