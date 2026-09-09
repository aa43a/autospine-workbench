function distanceSquared(p,a,b) {
  const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;
  const t=den ? Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) : 0;
  return (p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2;
}

export function brushHitsTriangle(center,radius,triangle) {
  const signs=triangle.map((a,i) => {
    const b=triangle[(i+1)%3];return (b[0]-a[0])*(center[1]-a[1])-(b[1]-a[1])*(center[0]-a[0]);
  });
  if (signs.every(v => v >= 0) || signs.every(v => v <= 0)) return true;
  return triangle.some((a,i) => distanceSquared(center,a,triangle[(i+1)%3]) <= radius*radius);
}

export function brushStrokePoints(previous,current,radius) {
  if (!previous) return [current];
  const count=Math.max(1,Math.ceil(Math.hypot(current[0]-previous[0],current[1]-previous[1])/Math.max(.5,radius/2)));
  return Array.from({length:count},(_,i) => previous.map((v,k) => v+(current[k]-v)*(i+1)/count));
}
