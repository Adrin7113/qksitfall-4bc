import * as k from './vendor/iso-kit.mjs';
import {SCENE} from './scene.mjs';
export {SCENE};

const base = SCENE.base;
export const projection = k.fitProjection([...k.boxCorners(base,-19,58),...k.boxCorners({x:157,y:43,w:97,d:74,r:2},-14,40)],760,500,{pad:45,azimuth:43,elevation:37});
const P=projection;
export const projectionBasis={x:k.axisVector(P,[1,0,0]),y:k.axisVector(P,[0,1,0]),depth:[Math.cos(P.azimuth*Math.PI/180)*Math.cos(P.elevation*Math.PI/180),Math.sin(P.azimuth*Math.PI/180)*Math.cos(P.elevation*Math.PI/180),Math.sin(P.elevation*Math.PI/180)]};
const slab=(plan,z,h,tone='mid',lit=false) => k.solidSvg(k.slabOf(plan,z,h,P,5,Math.min(0.8,h/3)),{tone,lit});
const plan=(x,y,w,d,r=1) => ({x,y,w,d,r});
const closed=(shape,z,tone='lo') => k.lineSvg(k.planOutline(shape,z,P,6),{tone});
const fasteners=(shape,z,inset=5) => k.dotsSvg(k.corners(shape,inset).map(([x,y])=>k.iso([x,y,z],P)),{size:0.7,tone:'mid'});

function charger(x){
  const foundation=plan(x-14,-88,28,28,3);
  const body=plan(x-10,-84,20,20,2.8);
  const display=plan(x-7,-64,14,1.1,0.7);
  return slab(foundation,0,3,'lo')+fasteners(foundation,3,3)+slab(body,3,43,'mid')+
    closed(k.insetPlan(body,2),46,'lo')+slab(plan(x-11,-85,22,22,3),46,3,'hi')+
    slab(display,28,13,'lo')+slab(plan(x-5.5,-62.9,11,0.5,0.3),30,8,'hi')+
    slab(plan(x-5,-62.4,7,0.4,0.3),32,1.3,'hi',true)+
    slab(plan(x-6,-64,3,0.6),19,3,'mid')+
    slab(plan(x+2,-64,4,0.6),19,3,'hi')+
    slab(plan(x-7,-64,14,0.4),8,4,'lo');
}

function car(id){
  const s=[];
  s.push(`<path class="iso-halo" d="${k.haloOf(plan(-22,-31,44,62,6),1,4,P)}"/>`);
  for(const y of [-22,19]) for(const x of [-23,18]) s.push(slab(plan(x,y,5,11,2),1,8,'lo'));
  s.push(slab(plan(-22,-32,44,64,7),7,5,'lo'));
  s.push(slab(plan(-22,-33,44,66,7),12,10,'hi',id==='A'));
  s.push(slab(plan(-18,-30,36,18,4),22,1.8,'hi',id==='A'));
  s.push(slab(plan(-18,-12,36,31,4),22,12,'mid'));
  s.push(slab(plan(-15,-9,30,22,4),34,2,'hi',id==='A'));
  s.push(slab(plan(-15,-12.5,30,3,1),26,7,'lo'));
  s.push(slab(plan(-15,17,30,2.2,1),25,7,'lo'));
  s.push(slab(plan(-18.3,-8,0.6,20,0.2),26,6,'lo'));
  s.push(slab(plan(17.7,-8,0.6,20,0.2),26,6,'lo'));
  for(const x of [-25,20])s.push(slab(plan(x,-12,5,6,1.4),24,3,'mid'));
  for(const x of [-17,9])s.push(slab(plan(x,-33.5,8,1,0.3),15,3,'hi'));
  s.push(slab(plan(-15,32.3,30,1.5,0.3),13,3,'lo'));
  s.push(closed(plan(-14,22,28,7,1),22,'lo'));
  return s.join('');
}

export function buildFigure(){
  const scene=[];
  const fixture=(id,x,y,z,body)=>`<g id="${id}" data-scene-item data-world-x="${x}" data-world-y="${y}" data-world-z="${z}">${body}</g>`;
  scene.push(`<path class="iso-halo" d="${k.haloOf(base,-19,14,P)}"/>`);
  for(const [x,y] of k.corners(base,20))scene.push(slab(plan(x-7,y-7,14,14,3),-19,5,'lo'));
  scene.push(slab(base,-14,14,'lo'));
  scene.push(slab(plan(157,43,97,74,2),-14,14,'lo'));
  scene.push(closed(k.insetPlan(base,5),0,'faint'),fasteners(base,0,9));
  scene.push(slab(SCENE.asphalt,0,0.8,'lo'));
  scene.push(slab(plan(157,44,97,72,1),0,.8,'lo'));
  for(const x of [-76,76])scene.push(closed(plan(x-39,SCENE.bay.y,78,103,2),0.9,'mid'));
  for(const id of ['A','B']){
    const [x,y]=SCENE.waiting[id];
    scene.push(closed(plan(x-34,y-42,68,84,2),.9,'lo'));
  }
  for(const y of [63,80,97])scene.push(slab(plan(-3,y,6,6,.6),.9,.2,'mid'));
  scene.push(slab(plan(-40,226,80,8,1),0,.6,'lo'));
  scene.push(k.faceTextSvg(k.topMatrix([0,231],.7,P,'x'),'EV / 02',{size:3,tone:'lo',anchor:'middle'}));
  const items=[];
  items.push(fixture('curb-left',-152,64,2,slab(plan(-154,-96,5,321,1.3),.8,3,'mid')));
  items.push(fixture('curb-right-back',152,-27,2,slab(plan(149,-96,5,132,1.3),.8,3,'mid')));
  items.push(fixture('curb-right-front',152,172,2,slab(plan(149,120,5,105,1.3),.8,3,'mid')));
  for(const x of [-76,76]){
    items.push(fixture('stop-'+x,x,-47.5,2.6,slab(plan(x-24,-50,48,5,1),.9,3.4,'mid')));
    items.push(fixture('charger-'+x,x,-74,24,charger(x)));
  }
  for(const [x,y] of [[-130,-95],[130,-95],[-165,220],[165,220]])items.push(fixture('bollard-'+x+'-'+y,x,y,7,slab(plan(x-3,y-3,6,6,1.5),.8,13,'mid')));
  items.push(fixture('car-a',...SCENE.waiting.A,18,car('A')).replace('id="car-a"',`id="car-a" data-car="A" transform="${k.translateAlong(P,[...SCENE.waiting.A,0])}"`));
  items.push(fixture('car-b',-76,SCENE.dockY,18,car('B')).replace('id="car-b"',`id="car-b" data-car="B" transform="${k.translateAlong(P,[-76,SCENE.dockY,0])}"`));
  scene.push(`<g id="scene-depth">${items.join('')}</g>`);
  return k.plateHtml({fig:'FIG 01',title:'A two-bay charging lot',hint:'Use the time buttons below',readout:'08:00 · B charges, A waits',
    keys:[{mark:'lit',label:'Car A · light body'},{mark:'raised',label:'Car B · shaded body'},{mark:'edge',label:'North = left bay · South = right bay'}],
    caption:'One 11 kW port per bay. Front wheels meet the wheel stop; completed cars leave through the right-hand exit.',
    body:`<div class="iso-stage" tabindex="0" role="group" aria-label="Charging lot. Left and right arrows inspect the early and late time slots.">${k.figureSvg({width:760,height:500,label:'A detailed two-bay charging lot with separate waiting spaces at the front and an exit to the right. North is the left bay and South is the right bay.',body:scene})}</div>`});
}
