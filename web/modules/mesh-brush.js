// Screen-space capsule hit testing: sparse pointer events must not leave stroke gaps.
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
function distance(p,a,b){
  const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
  const t=length?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)):0;
  return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);
}
function inside(p,triangle){
  const signs=triangle.map((v,i)=>cross(v,triangle[(i+1)%3],p));
  return signs.every(s=>s>=0)||signs.every(s=>s<=0);
}
function segmentDistance(a,b,c,d){
  const x=cross(a,b,c),y=cross(a,b,d),u=cross(c,d,a),v=cross(c,d,b);
  if(((x>0&&y<0)||(x<0&&y>0))&&((u>0&&v<0)||(u<0&&v>0)))return 0;
  return Math.min(distance(a,c,d),distance(b,c,d),distance(c,a,b),distance(d,a,b));
}
export function brushTriangles(mesh,width,height,start,end,radius){
  if(![width,height,radius,...start,...end].every(Number.isFinite)||width<=0||height<=0||radius<0)
    throw Error('invalid_brush_geometry');
  const hits=[];
  for(let i=0;i<mesh.triangles.length;i+=3){
    const triangle=mesh.triangles.slice(i,i+3).map(v=>[mesh.uvs[2*v]*width,mesh.uvs[2*v+1]*height]);
    if(Math.abs(cross(...triangle))<1e-10)continue;
    if(inside(start,triangle)||inside(end,triangle)||triangle.some((p,k)=>
      segmentDistance(start,end,p,triangle[(k+1)%3])<=radius))hits.push(i/3);
  }
  return hits;
}
