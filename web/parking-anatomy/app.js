const $=selector=>document.querySelector(selector);
const $$=selector=>Array.from(document.querySelectorAll(selector));
const money=n=>'₹'+n.toFixed(2);
const number=n=>n.toFixed(2);
const clock=minute=>{const total=Math.round(minute*60);return [Math.floor(total/3600),Math.floor(total/60)%60,total%60].map(n=>String(n).padStart(2,'0')).join(':');};
const bitString=bookings=>FIXTURE.options.map((o,i)=>bookings.some(b=>b.index===i)?'1':'0').join('');
let weight=0.25, mode='optimal', slot='early', selectedBits='01001', step=0;
let currentModel=scheduleAt(FIXTURE,weight);
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let touring=false;
const motion=new ParkingMotion({scene:SCENE,basis:PROJECTION_BASIS});
function interaction(){motion.interaction();}
$('.iso-stage').addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();interaction();slot=['ArrowLeft','Home'].includes(event.key)?'early':'late';renderLot();}});
function renderLot(){
 const a=currentModel.best.bookings.find(o=>o.vehicle_id==='A');
 const text=mode==='greedy'?(slot==='early'?'A takes North at 08:00. B needs the same port and has no feasible alternative.':'B missed its charging deadline. A has left the lot.'):(slot==='early'?(a.station_id==='South'?'Both cars charge: B at North and A at South.':'B charges at North. A waits in the entrance apron for the next hour.'):(a.slot_id==='late'?'B has left. A now charges at North and finishes before 10:00.':'Both cars have finished and left. Both bays are empty.'));
 $('#lot-caption').textContent=text;
 $$('[data-slot]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.slot===slot)));
 motion.setState({mode,slot,best:currentModel.best,readout:slot==='early'?'08:00 · '+(mode==='greedy'?'B blocked':a.station_id==='South'?'Both cars charging':'B charging · A waiting'):'09:00 · '+(mode==='greedy'?'B missed deadline':a.slot_id==='late'?'A charging · B finished':'Both cars finished')});
}

function renderTimeline(){
  const best=currentModel.best;
  const rows=['<div class="timeline-row" role="row"><div class="head" role="columnheader">Station</div><div class="head" role="columnheader">08:00–09:00</div><div class="head" role="columnheader">09:00–10:00</div></div>'];
  for(const station of ['North','South']){
    rows.push(`<div class="timeline-row" role="row"><div class="station" role="rowheader">${station}</div>`);
    for(const time of ['early','late']){
      if(mode==='greedy'&&station==='North'&&time==='early')rows.push('<div class="conflict" role="cell">A + B · conflict</div>');
      else{
        const booking=mode==='optimal'?best.bookings.find(o=>o.station_id===station&&o.slot_id===time):null;
        rows.push(booking?`<div class="booked" role="cell"><span class="car-chip ${booking.vehicle_id.toLowerCase()}">${booking.vehicle_id}</span>Car ${booking.vehicle_id}</div>`:'<div class="empty" role="cell">Available</div>');
      }
    }
    rows.push('</div>');
  }
  $('#timeline').innerHTML=rows.join('');
  $('#completion').innerHTML=mode==='optimal'?best.bookings.map(o=>`<span>Car ${o.vehicle_id} · charging complete ${clock(o.completion_minute)}</span>`).join(''):'<span>No complete schedule: both requests need the same early port.</span>';
}

function renderQuantum(){
  const options=currentModel.options;
  const chosen=energyOf(selectedBits,options);
  $('#booking-bits').innerHTML=options.map((o,i)=>`<button class="booking-bit" id="booking-${i}" data-bit="${i}" aria-pressed="${selectedBits[i]==='1'}" aria-label="x${i}: Car ${o.vehicle_id}, ${o.station_id}, ${o.slot_id==='early'?'08:00 to09:00':'09:00 to10:00'}, ${o.score.toFixed(2)} score points"><span class="bit-label">x${'₀₁₂₃₄'[i]}</span><span class="booking-info">Car ${o.vehicle_id} · ${o.station_id}<small>${o.slot_id==='early'?'08:00–09:00':'09:00–10:00'} · ${money(o.electricity_cost_rupees)} + ${o.waiting_minutes} min wait</small></span><span class="booking-score">${number(o.score)}<small> pts</small></span><span class="bit-toggle">${selectedBits[i]}</span></button>`).join('');
  $('#bit-string').innerHTML=Array.from(selectedBits).map(bit=>`<span data-on="${bit==='1'}">${bit}</span>`).join('');
  $('#energy-objective').textContent=number(chosen.objective);$('#energy-penalty').textContent=number(chosen.penalty);$('#energy-total').textContent=number(chosen.energy);
  $('#energy-status').textContent=chosen.feasible?'Valid · one booking for each car, no double booking.':chosen.reasons.join(' ');
  $('#energy-status').classList.toggle('invalid',!chosen.feasible);
  $('#states').innerHTML=encodedStates(options).map(s=>`<button data-encoding="${s.bits}" class="state-choice${s.feasible?' feasible':''}${s.bits===selectedBits?' selected':''}" aria-label="${s.bits}, ${s.feasible?'feasible':'infeasible'}, energy ${number(s.energy)}" aria-pressed="${s.bits===selectedBits}">${s.bits}<small>${number(s.energy)}${s.feasible?' · valid':''}</small></button>`).join('');
  renderStep();
}

const steps=[
  ['FROM BOOKINGS TO ENERGY','Make bad schedules expensive.','Use the five booking scores as costs. Add penalties for missing cars, multiple bookings for A, and the shared charger conflict. A low-energy valid bitstring is a low-score schedule.','The three conflict-free plans have zero constraint penalty.'],
  ['FIVE QUBITS, REPEATED LAYERS','Let cost and mixing shape the state.','Prepare each qubit with an H gate to make |+⟩. Alternate a cost layer generated by H꜀ with an X mixer. The cost layer includes interactions between qubits for the booking constraints. Repeat for p layers; γ and β control each layer.','The circuit above shows the actual coupled cost evolution exp(−iγH꜀), including the RZZ connections. The mixer is exp(−iβΣXᵢ).'],
  ['A CLASSICAL OPTIMIZER CLOSES THE LOOP','Tune the angles. Measure many times.','Estimate energy from circuit runs. A classical optimizer adjusts γ and β, then runs the circuit again. Finally, take many measurement shots at the chosen angles. Each shot returns one bitstring.','The repository implements this workflow with local Qiskit Aer. No quantum circuit or measurement histogram is simulated on this page.'],
  ['FROM BITS BACK TO BOOKINGS','Read a scheduling answer.','Treat every 1 as a selected booking. Check that every driver has exactly one session and no charger is double-booked. Compare the best feasible sample with the checked classical answer.','A quantum sample is a candidate, not a certificate of optimality.']
];
function renderStep(){
  const [kicker,title,copy,detail]=steps[step];$('#step-kicker').textContent=kicker;$('#step-title').textContent=title;$('#step-copy').textContent=copy;$('#step-detail').textContent=detail;
  $$('[data-step]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.step)===step)));
  const best=currentModel.best;
  const visual=step===0?'<div class="visual-formula">score + penalties<small>VALID PLAN → ZERO PENALTY</small></div>':step===1?'<div class="visual-formula">H → RZ / RZZ → RX<small>THE ACTUAL CIRCUIT IS SHOWN ABOVE</small></div>':step===2?'<div class="sample-visual">γ ↔ β<small>CLASSICAL OPTIMIZER ↔ CIRCUIT<br>Repeated shots return candidate strings.</small></div>':`<div class="decoded-visual">${bitString(best.bookings)}<p>${best.bookings.map(o=>`${o.vehicle_id} → ${o.station_id} / ${o.slot_id==='early'?'08:00':'09:00'}`).join('<br>')}</p></div>`;
  $('#step-visual').innerHTML=visual;
}

function render(){
  currentModel=scheduleAt(FIXTURE,weight);
  const best=currentModel.best;
  $('#weight-value').textContent=number(weight);$('#weight-equation').textContent=number(weight);
  $('#weight').value=weight;$('#weight').setAttribute('aria-valuetext',number(weight)+' points per minute of waiting');
  $$('[data-weight]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.weight)===weight)));
  $$('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));
  $('#bill').textContent=mode==='optimal'?money(best.cost):'—';
  $('#wait').innerHTML=mode==='optimal'?best.waiting+' <small>min</small>':'—';
  $('#score').innerHTML=mode==='optimal'?number(best.score)+' <small>pts</small>':'—';
  $('#result-label').textContent=mode==='optimal'?'Both cars get a slot.':'Charger conflict. B has no slot.';
  $('#strategy-note').textContent=mode==='greedy'?'A’s individually cheapest score still chooses North early. B needs the same slot. A request that looks best alone cannot serve both drivers.':best.bookings[0].station_id==='South'?'At this waiting weight, A’s shorter wait at South is worth the higher bill. B keeps North’s early slot.':'A’s individual favorite blocks B. Giving North’s early slot to B leaves both drivers a booking.';
  $('#reason-copy').textContent=mode==='greedy'?'The first choice looks good for A, but gives B no feasible session. A complete solution must check the combination, including shared charger capacity.':'A can use either station in either hour. B can only use North at 08:00. Looking at the whole schedule makes room for both.';
  renderTimeline();renderLot();renderQuantum();renderCircuit(FIXTURE,weight);if($('#penalty-value'))$('#penalty-value').textContent=number(safePenalty(currentModel.options));
}

$('#weight').addEventListener('input',event=>{interaction();weight=Number(event.target.value);currentModel=scheduleAt(FIXTURE,weight);selectedBits=bitString(currentModel.best.bookings);render();});
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;interaction();
  if(button.dataset.weight!==undefined){weight=Number(button.dataset.weight);currentModel=scheduleAt(FIXTURE,weight);selectedBits=bitString(currentModel.best.bookings);render();}
  if(button.dataset.slot){slot=button.dataset.slot;renderLot();}
  if(button.dataset.mode){mode=button.dataset.mode;selectedBits=mode==='greedy'?'10001':bitString(currentModel.best.bookings);render();}
  if(button.dataset.bit!==undefined){const index=Number(button.dataset.bit);selectedBits=Array.from(selectedBits,(bit,i)=>i===index?(bit==='1'?'0':'1'):bit).join('');renderQuantum();$('#booking-'+index).focus({preventScroll:true});}
  if(button.dataset.encoding){selectedBits=button.dataset.encoding;renderQuantum();}
  if(button.dataset.step!==undefined){step=Number(button.dataset.step);renderStep();}
  if(button.id==='winning-bits'){selectedBits=bitString(currentModel.best.bookings);renderQuantum();}
  if(button.id==='theme'){const next=document.body.dataset.theme==='dark'?'light':'dark';document.body.dataset.theme=next;button.setAttribute('aria-label','Switch to '+(next==='dark'?'light':'dark')+' theme');}
  if(button.id==='tour'){touring=!touring;button.setAttribute('aria-pressed',String(touring));button.textContent=touring?'Ⅱ Pause tour':'▶ Auto tour';motion.setTour(touring,()=>{slot=slot==='early'?'late':'early';renderLot();});}
});
reduced.addEventListener('change',()=>{if(reduced.matches){touring=false;motion.setTour(false);$('#tour').setAttribute('aria-pressed','false');$('#tour').textContent='▶ Auto tour';}});
$('#theme').setAttribute('aria-label','Switch to '+(document.body.dataset.theme==='dark'?'light':'dark')+' theme');
render();
window.parkingLab={motion,get state(){return {weight,mode,slot,selectedBits,best:currentModel.best};},fixture:FIXTURE};
