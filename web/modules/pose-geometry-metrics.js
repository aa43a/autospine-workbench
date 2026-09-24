// Same setup-space limits as character43/deformation_qa.py; current frame only.
export function createGeometryMetrics(setup, triangles) {
  const valid = points => points.length === setup.length && points.every(p =>
    Array.isArray(p) && p.length === 2 && p.every(Number.isFinite));
  const area = (p,t) => {const [a,b,c]=t.map(i=>p[i]);return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;};
  if (!valid(setup) || !triangles.length || triangles.some(t=>t.length!==3||t.some(i=>!Number.isInteger(i)||i<0||i>=setup.length)))
    throw Error('网格诊断输入无效');
  const areas=triangles.map(t=>area(setup,t));
  const edges=[...new Set(triangles.flatMap(t=>t.map((v,i)=>[v,t[(i+1)%3]].sort((a,b)=>a-b).join(','))))].map(key=>key.split(',').map(Number));
  const distance=(p,[a,b])=>Math.hypot(p[a][0]-p[b][0],p[a][1]-p[b][1]);
  const lengths=edges.map(e=>distance(setup,e));
  if (areas.some(a=>Math.abs(a)<1e-10)||lengths.some(v=>v<1e-10))throw Error('初始网格退化，无法评估');
  return points=>{
    if(!valid(points))throw Error('当前网格包含无效坐标');
    const ratios=triangles.map((t,i)=>area(points,t)/areas[i]);
    const stretches=edges.map((e,i)=>distance(points,e)/lengths[i]);
    const badTriangles=ratios.flatMap((r,i)=>r<.5||r>2?[i]:[]);
    const badEdges=edges.filter((e,i)=>stretches[i]>2);
    return {inversions:ratios.filter(r=>r<=0).length,badTriangles,badEdges,
      minAreaRatio:Math.min(...ratios),maxAreaRatio:Math.max(...ratios),maxEdgeStretch:Math.max(...stretches),
      passed:badTriangles.length===0&&badEdges.length===0};
  };
}
