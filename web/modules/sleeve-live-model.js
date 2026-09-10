// Draft-only FK preview: same unanimous garment ownership rule, no corrective bake.
const rotate = (p, degrees) => {const a=degrees*Math.PI/180;return [p[0]*Math.cos(a)-p[1]*Math.sin(a),p[0]*Math.sin(a)+p[1]*Math.cos(a)];};
export function sleeveLivePoints(record, assignments, bones, mesh, angles, rigidHand=false) {
  const chain=record.bone_ids.map(id=>bones.find(b=>b.id===id));
  if (chain.some(b=>!b) || !mesh || assignments.length!==record.triangles.length) throw Error('即时预览来源不完整');
  const roles=record.vertices_xy.map(()=>new Set());
  record.triangles.forEach((t,i)=>t.forEach(v=>roles[v].add(assignments[i].role)));
  const transforms=new Map();
  chain.forEach((b,i)=>{
    let head=b.head_xy.slice(), delta=angles[i]||0;
    if(i){const parent=transforms.get(chain[i-1].id);const offset=rotate(b.head_xy.map((x,k)=>x-chain[i-1].head_xy[k]),parent.delta);head=offset.map((x,k)=>x+parent.head[k]);delta+=parent.delta;}
    transforms.set(b.id,{head,delta});
  });
  const move=(p,b)=>{const f=transforms.get(b.id),v=rotate(p.map((x,k)=>x-b.head_xy[k]),f.delta);return v.map((x,k)=>x+f.head[k]);};
  return record.vertices_xy.map((point,i)=>{
    const set=roles[i], w=chain.map(b=>mesh.weights[i].filter(x=>x.bone_id===b.id).reduce((s,x)=>s+x.weight,0));
    if(rigidHand && set.has('hand') && !set.has('unknown')){w[0]=0;w[1]=0;w[2]=1;}
    const garment=set.size===1 && (set.has('sleeve')||set.has('hanging_cloth'));
    if(garment){w[1]+=w[2];w[2]=0;}
    const positions=chain.map(b=>move(point,b));
    if(set.size===1 && set.has('hanging_cloth')){
      // Wrist-rooted helper inherits forearm rotation; matches initial helper drive.
      const pivot=move(chain[2].head_xy,chain[1]);
      const offset=rotate(point.map((x,k)=>x-chain[2].head_xy[k]),transforms.get(chain[1].id).delta+(angles[3]||0));
      positions[1]=offset.map((x,k)=>x+pivot[k]);
    }
    return [0,1].map(k=>positions.reduce((s,p,j)=>s+p[k]*w[j],0));
  });
}

export function sleeveLiveAngles(time, motion) {
  const a=Math.sin(time*Math.PI)*30;
  if(motion==='hand')return [0,0,a,0];
  if(motion==='forearm')return [0,a,0,0];
  if(motion==='cloth')return [0,0,0,a/3];
  return [0,a,motion==='opposed'?-a:a,a/3];
}

export function drawSleeveTriangle(ctx, image, source, destination) {
  const [a,b,c]=source,[p,q,r]=destination;
  const ux=b[0]-a[0],uy=b[1]-a[1],vx=c[0]-a[0],vy=c[1]-a[1],det=ux*vy-uy*vx;
  if(Math.abs(det)<1e-10)return;
  const dx=q[0]-p[0],dy=q[1]-p[1],ex=r[0]-p[0],ey=r[1]-p[1];
  const A=(dx*vy-ex*uy)/det,B=(dy*vy-ey*uy)/det,C=(ex*ux-dx*vx)/det,D=(ey*ux-dy*vx)/det;
  ctx.save();ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.lineTo(...r);ctx.closePath();ctx.clip();
  ctx.transform(A,B,C,D,p[0]-A*a[0]-C*a[1],p[1]-B*a[0]-D*a[1]);ctx.drawImage(image,0,0);ctx.restore();
}
