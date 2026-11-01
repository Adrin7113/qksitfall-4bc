export const SCENE = {
  base: {x:-178,y:-111,w:356,d:351,r:10},
  asphalt: {x:-157,y:-95,w:314,d:319,r:5},
  car: {halfWidth:25,minY:-33.5,maxY:33.8,frontTireY:-22},
  wheelStop: {y:-50,d:5},
  stations: {North:{x:-76},South:{x:76}},
  bay: {y:-62,w:78,d:103},
  waiting: {A:[-100,180],B:[100,180]},
  exit:[284,80],
  aisleY:80,
  clearance:4,
};
SCENE.dockY=SCENE.wheelStop.y+SCENE.wheelStop.d-SCENE.car.frontTireY;
export function sceneTargets({mode,slot,best}, scene=SCENE){
  if(mode==='greedy') return {A:slot==='early'?[-76,scene.dockY]:null,B:[...scene.waiting.B]};
  const targets={};
  for(const id of ['A','B']){
    const booking=best.bookings.find(b=>b.vehicle_id===id);
    targets[id]=booking.slot_id===slot?[scene.stations[booking.station_id].x,scene.dockY]:slot==='early'?[...scene.waiting[id]]:null;
  }
  return targets;
}
export function sceneRoute(from,to,scene=SCENE){
  const destination=to||scene.exit;
  if(Math.hypot(from[0]-destination[0],from[1]-destination[1])<.01)return [];
  const points=[[from[0],scene.aisleY],[destination[0],scene.aisleY],destination];
  return points.filter((p,i)=>Math.hypot(p[0]-(i?points[i-1][0]:from[0]),p[1]-(i?points[i-1][1]:from[1]))>.01).map(p=>[...p]);
}
