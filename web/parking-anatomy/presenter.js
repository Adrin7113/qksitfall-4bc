// Four chapters, one reproducible walkthrough. Both algorithm demos stay independent.
const demoChapterIds=['lot','shared-power','quantum','results'];
function setQuantumModel(name,{focus=false}={}) {
 if(!['booking','shared'].includes(name))return;
 for(const tab of document.querySelectorAll('[data-quantum-model]')) {
  const selected=tab.dataset.quantumModel===name;
  tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
  document.getElementById(tab.getAttribute('aria-controls')).hidden=!selected;
  if(selected&&focus)tab.focus({preventScroll:true});
 }
}
function revealDemoTarget(target) {
 const panel=target.closest('[role="tabpanel"]');
 if(panel)setQuantumModel(panel.id==='quantum-shared'?'shared':'booking');
 for(let ancestor=target;ancestor;ancestor=ancestor.parentElement)if(ancestor.tagName==='DETAILS')ancestor.open=true;
}
function markDemoChapter(id) {
 for(const link of document.querySelectorAll('[data-chapter-link]')) {
  if(link.dataset.chapterLink===id)link.setAttribute('aria-current','step');
  else link.removeAttribute('aria-current');
 }
}
function navigateDemo(hash,{replace=false}={}) {
 const target=document.getElementById(hash.slice(1));if(!target)return;
 revealDemoTarget(target);
 history[replace?'replaceState':'pushState'](null,'',hash);
 markDemoChapter(target.closest('.demo-chapter')?.id||'lot');
 target.setAttribute('tabindex','-1');target.focus({preventScroll:true});
 target.scrollIntoView({behavior:reduced.matches?'auto':'smooth',block:'start'});
}
function resetDemo() {
 touring=false;motion.setTour(false);
 document.getElementById('tour').setAttribute('aria-pressed','false');
 document.getElementById('tour').textContent='▶ Auto tour';
 weight=.25;mode='optimal';slot='early';step=0;
 currentModel=scheduleAt(FIXTURE,weight);selectedBits=bitString(currentModel.best.bookings);
 sharedBits=FIXTURE.shared_power.presets.delayed;sharedSelection='delayed';
 for(const details of document.querySelectorAll('main details'))details.open=false;
 setQuantumModel('booking');render();renderSharedPower();renderQuantumRule('one');renderBenchmark('original');
 navigateDemo('#top',{replace:true});
}
function initDemoEvidence() {
 const data=FIXTURE.shared_power;
 const start=sharedEnergy(data,data.presets.delayed),exact=sharedEnergy(data,data.reference.bits.join(''));
 const sampled=data.saved_run.status==='feasible'?sharedEnergy(data,data.saved_run.bits.join('')):null;
 document.getElementById('result-time-comparison').innerHTML=`${start.average} → ${exact.average} <small>min</small>`;
 document.getElementById('result-comparison-rows').innerHTML=[['Valid starting plan',start],['Classical exact reference',exact],['Best saved QAOA sample',sampled]].map(([name,result])=>`<tr><th scope="row">${name}</th><td>${result?result.average+' min':'No feasible sample'}</td><td>${result?result.objective+' min':'—'}</td><td>${result?Math.max(...result.plans.map(p=>p.completion_minute))+' min':'—'}</td></tr>`).join('');
}
document.addEventListener('click',event=>{
 const tab=event.target.closest('[data-quantum-model]');
 if(tab){setQuantumModel(tab.dataset.quantumModel);return;}
 if(event.target.closest('[data-reset-demo]')){resetDemo();return;}
 const jump=event.target.closest('[data-jump]');
 if(jump){navigateDemo('#'+jump.dataset.jump);return;}
 const link=event.target.closest('a[href^="#"]');
 if(link&&document.getElementById(link.hash.slice(1))){event.preventDefault();navigateDemo(link.hash);}
});
document.querySelector('.quantum-tabs').addEventListener('keydown',event=>{
 if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
 event.preventDefault();
 const current=event.target.closest('[data-quantum-model]')?.dataset.quantumModel;
 const next=event.key==='Home'?'booking':event.key==='End'?'shared':current==='booking'?'shared':'booking';
 setQuantumModel(next,{focus:true});
});
let demoScrollFrame=0;
function updateDemoChapter() {
 demoScrollFrame=0;
 const nav=document.querySelector('.demo-nav'),offset=nav.getBoundingClientRect().height+24;
 document.documentElement.style.setProperty('--demo-offset',offset+'px');
 let current='lot';
 for(const id of demoChapterIds)if(document.getElementById(id).getBoundingClientRect().top<=offset+64)current=id;
 markDemoChapter(current);
}
window.addEventListener('scroll',()=>{if(!demoScrollFrame)demoScrollFrame=requestAnimationFrame(updateDemoChapter);},{passive:true});
window.addEventListener('resize',updateDemoChapter);
window.addEventListener('hashchange',()=>{const target=document.getElementById(location.hash.slice(1));if(target){revealDemoTarget(target);target.scrollIntoView({block:'start'});}});
initDemoEvidence();updateDemoChapter();
if(location.hash){const target=document.getElementById(location.hash.slice(1));if(target){revealDemoTarget(target);requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));}}
