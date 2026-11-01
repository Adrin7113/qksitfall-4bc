import assert from 'node:assert/strict';
import {SCENE,sceneTargets,sceneRoute} from './scene.mjs';
import {projection,projectionBasis,buildFigure} from './geometry.mjs';
import {axisVector} from './vendor/iso-kit.mjs';
assert.equal(SCENE.dockY,-23);
assert.equal(SCENE.dockY+SCENE.car.frontTireY,SCENE.wheelStop.y+SCENE.wheelStop.d);
for(const station of Object.values(SCENE.stations)){
 assert.ok(station.x-SCENE.car.halfWidth>=station.x-SCENE.bay.w/2);
 assert.ok(SCENE.dockY+SCENE.car.minY>-64+SCENE.clearance);
}
for(const [id,[x,y]] of Object.entries(SCENE.waiting)){
 assert.ok(x-SCENE.car.halfWidth>=SCENE.asphalt.x);
 assert.ok(x+SCENE.car.halfWidth<=SCENE.asphalt.x+SCENE.asphalt.w);
 assert.ok(y+SCENE.car.maxY<=SCENE.asphalt.y+SCENE.asphalt.d);
 assert.ok(y+SCENE.car.minY>SCENE.aisleY+SCENE.car.maxY+SCENE.clearance);
}
for(const weight of [.25,1])for(const mode of ['optimal','greedy'])for(const slot of ['early','late']){
 const best={bookings:[{vehicle_id:'A',station_id:weight===1?'South':'North',slot_id:weight===1?'early':'late'},{vehicle_id:'B',station_id:'North',slot_id:'early'}]};
 const targets=sceneTargets({mode,slot,best});
 if(mode==='optimal'&&weight===1&&slot==='late')assert.deepEqual(targets,{A:null,B:null});
 for(const id of ['A','B'])for(const to of [targets[id]]){
  const from=SCENE.waiting[id],route=sceneRoute(from,to);
  if(route.length)assert.deepEqual(route.at(-1),to||SCENE.exit);
 }
}
assert.deepEqual(projectionBasis.x,axisVector(projection,[1,0,0]));
assert.deepEqual(projectionBasis.y,axisVector(projection,[0,1,0]));
assert.ok(SCENE.exit[0]-SCENE.car.halfWidth>254+SCENE.clearance);
const html=buildFigure();assert.ok(html.includes('scene-depth'));assert.ok(html.includes('data-car="A"'));
console.log('Passed: dock contact, charger clearance, waiting/aisle separation, all scene targets, exit, and shared projection.');

// Drive the actual browser controller through all poses and interrupted moves.
const {readFileSync}=await import('node:fs');
const vm=await import('node:vm');
let now=0,nextId=0;const frames=new Map();
function node(id,x=0,y=0,z=0){return {id,dataset:{worldX:x,worldY:y,worldZ:z},style:{},setAttribute(){},textContent:''};}
const carA=node('car-a',...SCENE.waiting.A,18),carB=node('car-b',-76,SCENE.dockY,18);carA.dataset.car='A';carB.dataset.car='B';
const stage=node('stage'),readout=node('readout');
const layer={children:[carA,carB],appendChild(n){this.children=this.children.filter(i=>i!==n);this.children.push(n);}};
const context=vm.createContext({SCENE,PROJECTION_BASIS:projectionBasis,Math,JSON,performance:{now:()=>now},
 document:{hidden:false,querySelector:s=>s==='.iso-stage'?stage:readout,getElementById:id=>id==='scene-depth'?layer:id==='car-a'?carA:carB,addEventListener(){}},
 matchMedia:()=>({matches:false,addEventListener(){}}),IntersectionObserver:class{observe(){}},
 requestAnimationFrame:fn=>{frames.set(++nextId,fn);return nextId;},cancelAnimationFrame:id=>frames.delete(id),setTimeout:()=>0,clearTimeout(){}});
vm.runInContext(readFileSync(new URL('./motion.js',import.meta.url),'utf8')+';this.controller=new ParkingMotion({scene:SCENE,basis:PROJECTION_BASIS});',context);
const controller=context.controller;
const states=[];for(const weight of [.25,1])for(const mode of ['optimal','greedy'])for(const slot of ['early','late'])states.push({mode,slot,best:{bookings:[{vehicle_id:'A',station_id:weight===1?'South':'North',slot_id:weight===1?'early':'late'},{vehicle_id:'B',station_id:'North',slot_id:'early'}]}});
function advance(){
 now+=1000/60;const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(now));
 if(carA.style.visibility!=='hidden'&&carB.style.visibility!=='hidden'){
 const [ax,ay]=controller.positions.A,[bx,by]=controller.positions.B;
 assert.ok(Math.abs(ax-bx)>=SCENE.car.halfWidth*2||Math.abs(ay-by)>=SCENE.car.maxY-SCENE.car.minY,`Car collision at A=${ax},${ay} B=${bx},${by}`);
 }
}
function settle(){for(let i=0;i<1500&&frames.size;i++)advance();assert.equal(frames.size,0);assert.equal(controller.queue.length,0);}
for(const first of states)for(const second of states){controller.setState(first);settle();controller.setState(second);settle();}
for(let i=0;i<120;i++){controller.setState(states[(i*7)%states.length]);for(let frame=0;frame<(i%13)+1;frame++)advance();}
settle();assert.ok(stage.dataset.motionStats);
console.log('Passed: actual controller all 64 pose transitions and 120 rapid interruptions, with sampled car collision checks and stopped settled RAF.');
