class ParkingMotion {
  constructor({scene,basis,onSettled=()=>{}}){
    this.scene=scene;this.basis=basis;this.onSettled=onSettled;
    this.stage=document.querySelector('.iso-stage');this.layer=document.getElementById('scene-depth');this.readout=document.querySelector('[data-readout]');
    this.cars=Object.fromEntries(['A','B'].map(id=>[id,document.getElementById('car-'+id.toLowerCase())]));
    this.positions={A:[...scene.waiting.A],B:[scene.stations.North.x,scene.dockY]};
    this.items=[...this.layer.children].map(node=>({node,id:node.dataset.car,point:[Number(node.dataset.worldX),Number(node.dataset.worldY),Number(node.dataset.worldZ)]}));
    this.visible=true;this.raf=0;this.queue=[];this.segment=null;this.stamp=0;this.timer=0;this.tour=false;this.first=true;
    this.reduced=matchMedia('(prefers-reduced-motion: reduce)');this.stats={frames:0,maxWorkMs:0,longFrames:0,totalFrameMs:0,intervals:0};
    this.tick=this.tick.bind(this);
    this.observer=new IntersectionObserver(entries=>{this.visible=entries.at(-1).isIntersecting;this.resume();},{rootMargin:'80px'});this.observer.observe(this.stage);
    document.addEventListener('visibilitychange',()=>this.resume());
    this.reduced.addEventListener('change',()=>{if(this.reduced.matches&&this.state)this.setState(this.state);else this.resume();});
    this.paint();
  }
  targets({mode,slot,best}){
    const s=this.scene;
    if(mode==='greedy')return {A:slot==='early'?[s.stations.North.x,s.dockY]:null,B:[...s.waiting.B]};
    return Object.fromEntries(['A','B'].map(id=>{const b=best.bookings.find(b=>b.vehicle_id===id);return [id,b.slot_id===slot?[s.stations[b.station_id].x,s.dockY]:slot==='early'?[...s.waiting[id]]:null];}));
  }
  route(from,destination){
    const to=destination||this.scene.exit;if(Math.hypot(from[0]-to[0],from[1]-to[1])<.01)return [];const points=[[from[0],this.scene.aisleY],[to[0],this.scene.aisleY],to];
    let previous=from;return points.filter(point=>{const keep=Math.hypot(point[0]-previous[0],point[1]-previous[1])>.01;previous=point;return keep;}).map(p=>[...p]);
  }
  setState(state){
    const interrupted=this.segment?.id;
    this.state=state;this.finalReadout=state.readout||'';this.targetsNow=this.targets(state);
    cancelAnimationFrame(this.raf);this.raf=0;this.stamp=0;this.segment=null;this.queue=[];clearTimeout(this.timer);this.timer=0;
    if(this.reduced.matches||this.first){
      for(const id of ['A','B']){this.positions[id]=[...(this.targetsNow[id]||this.scene.exit)];this.cars[id].style.visibility=this.targetsNow[id]?'visible':'hidden';}
      this.first=false;this.paint();this.finish();return;
    }
    const moving=['A','B'].filter(id=>{const to=this.targetsNow[id]||this.scene.exit;return Math.hypot(this.positions[id][0]-to[0],this.positions[id][1]-to[1])>.01;});
    moving.sort((a,b)=>(a===interrupted?-1:b===interrupted?1:this.positions[a][1]-this.positions[b][1]));
    const virtual=Object.fromEntries(['A','B'].map(id=>[id,[...this.positions[id]]]));
    const append=(id,to,hide=false)=>{
      const route=this.route(virtual[id],to);
      for(let i=0;i<route.length;i++)this.queue.push({id,to:route[i],hide:hide&&i===route.length-1});
      if(route.length)virtual[id]=[...route.at(-1)];
    };
    // Clear the shared driving aisle before dispatching any arriving car.
    // An interrupted car clears first, preventing a second car crossing it.
    for(const id of moving){
      if(!this.targetsNow[id])append(id,null,true);
      else if(this.cars[id].style.visibility!=='hidden'&&Math.hypot(virtual[id][0]-this.scene.waiting[id][0],virtual[id][1]-this.scene.waiting[id][1])>.01)append(id,this.scene.waiting[id]);
    }
    for(const id of moving)if(this.targetsNow[id])append(id,this.targetsNow[id]);
    for(const id of ['A','B'])if(!moving.includes(id))this.cars[id].style.visibility=this.targetsNow[id]?'visible':'hidden';
    if(this.queue.length)this.readout.textContent='Moving through the aisle…';else this.finish();
    this.resume();
  }
  easing(t){
    let low=0,high=1,u=t;
    const bezier=(v,a,b)=>3*(1-v)*(1-v)*v*a+3*(1-v)*v*v*b+v*v*v;
    for(let i=0;i<10;i++){u=(low+high)/2;if(bezier(u,.2,.38)<t)low=u;else high=u;}
    return bezier(u,0,.9);
  }
  tick(now){
    this.raf=0;const started=performance.now();
    if(!this.visible||document.hidden||this.reduced.matches){this.stamp=0;return;}
    const delta=this.stamp?Math.min(now-this.stamp,50):0;
    if(this.stamp){this.stats.totalFrameMs+=now-this.stamp;this.stats.intervals++;}this.stamp=now;
    if(!this.segment&&this.queue.length){
      const next=this.queue.shift(),from=[...this.positions[next.id]];
      this.segment={...next,from,elapsed:0,duration:Math.max(180,Math.min(520,Math.hypot(next.to[0]-from[0],next.to[1]-from[1])*2.2))};
      this.cars[next.id].style.visibility='visible';
    }
    if(this.segment){
      const s=this.segment;s.elapsed+=delta;const progress=Math.min(1,s.elapsed/s.duration),eased=this.easing(progress);
      this.positions[s.id]=s.from.map((v,i)=>v+(s.to[i]-v)*eased);
      if(progress===1){this.positions[s.id]=[...s.to];if(s.hide)this.cars[s.id].style.visibility='hidden';this.segment=null;}
      this.paint();
    }
    this.stats.frames++;const work=performance.now()-started;this.stats.maxWorkMs=Math.max(this.stats.maxWorkMs,work);if(work>50)this.stats.longFrames++;
    if(this.segment||this.queue.length)this.raf=requestAnimationFrame(this.tick);else{this.stamp=0;this.finish();}
  }
  paint(){
    const b=this.basis;
    for(const id of ['A','B']){
      const [x,y]=this.positions[id],node=this.cars[id];
      node.setAttribute('transform',`translate(${(x*b.x[0]+y*b.y[0]).toFixed(3)} ${(x*b.x[1]+y*b.y[1]).toFixed(3)})`);
      node.dataset.worldX=x.toFixed(3);node.dataset.worldY=y.toFixed(3);
    }
    const ordered=[...this.items].sort((a,c)=>{const p=a.id?[...this.positions[a.id],18]:a.point,q=c.id?[...this.positions[c.id],18]:c.point;return p.reduce((v,n,i)=>v+n*b.depth[i],0)-q.reduce((v,n,i)=>v+n*b.depth[i],0);});
    const key=ordered.map(i=>i.node.id).join('|');if(key!==this.order){for(const item of ordered)this.layer.appendChild(item.node);this.order=key;}
    this.stage.dataset.moving=String(Boolean(this.segment||this.queue.length));
  }
  finish(){this.stage.dataset.moving='false';this.stage.dataset.motionStats=JSON.stringify(this.diagnostics);this.readout.textContent=this.finalReadout;this.onSettled();this.scheduleTour();}
  resume(){
    if(!this.visible||document.hidden||this.reduced.matches){cancelAnimationFrame(this.raf);this.raf=0;this.stamp=0;clearTimeout(this.timer);this.timer=0;return;}
    if((this.segment||this.queue.length)&&!this.raf){this.stamp=0;this.raf=requestAnimationFrame(this.tick);}else if(!this.segment&&!this.queue.length)this.scheduleTour();
  }
  setTour(enabled,callback){this.tour=enabled;this.tourCallback=callback;this.interaction();}
  interaction(){clearTimeout(this.timer);this.timer=0;this.scheduleTour();}
  scheduleTour(){clearTimeout(this.timer);this.timer=0;if(this.tour&&!this.reduced.matches&&this.visible&&!document.hidden&&!this.segment&&!this.queue.length)this.timer=setTimeout(()=>{this.timer=0;this.tourCallback?.();},4500);}
  get diagnostics(){return {...this.stats,active:Boolean(this.raf),queued:this.queue.length,positions:this.positions,visible:this.visible,reduced:this.reduced.matches,fps:this.stats.intervals?1000*this.stats.intervals/this.stats.totalFrameMs:0};}
}
