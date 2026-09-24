// Canvas coordinates use normalized UV or world XY with an upward Y axis.
export function viewCanvas(canvas,state,mode,onEdit) {
  const ctx=canvas.getContext('2d');canvas.width=640;canvas.height=480;
  canvas.tabIndex=0;
  canvas.style.cssText='width:100%;max-width:640px;touch-action:none;background:#17232e';
  let scale=1,cx=0,cy=0,drag=null,image=null;
  const aspect=()=>mode==='uv'&&image?image.height/image.width:1;
  const points=()=>mode==='uv'?state.controls.target_uv:state.points;
  const screen=p=>[320+(p[0]-cx)*scale,240+(mode==='uv'?1:-1)*(p[1]-cy)*scale*aspect()];
  const world=p=>[cx+(p[0]-320)/scale,cy+(mode==='uv'?1:-1)*(p[1]-240)/scale/aspect()];
  const mouse=e=>{const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*640/r.width,(e.clientY-r.top)*480/r.height];};
  function fit(){
    const p=mode==='uv'?[[0,0],[1,1]]:points(),xs=p.map(v=>v[0]),ys=p.map(v=>v[1]);
    cx=(Math.min(...xs)+Math.max(...xs))/2;cy=(Math.min(...ys)+Math.max(...ys))/2;
    scale=Math.min(560/Math.max(1e-6,Math.max(...xs)-Math.min(...xs)),400/Math.max(1e-6,(Math.max(...ys)-Math.min(...ys))*aspect()));draw();
  }
  function texture(triangle){
    const uv=triangle.map(i=>state.controls.target_uv[i].map((v,k)=>v*(k?image.height:image.width)));
    const xy=triangle.map(i=>screen(state.points[i]));
    const [u,v,w]=uv,[a,b,c]=xy,dx=v[0]-u[0],dy=v[1]-u[1],ex=w[0]-u[0],ey=w[1]-u[1],det=dx*ey-ex*dy;
    if(Math.abs(det)<1e-8)return;
    const m=(k)=>[((b[k]-a[k])*ey-(c[k]-a[k])*dy)/det,((c[k]-a[k])*dx-(b[k]-a[k])*ex)/det];
    const [xx,xyv]=m(0),[yx,yy]=m(1);
    ctx.save();ctx.beginPath();xy.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.clip();
    ctx.setTransform(xx,yx,xyv,yy,a[0]-xx*u[0]-xyv*u[1],a[1]-yx*u[0]-yy*u[1]);ctx.drawImage(image,0,0);ctx.restore();
  }
  function draw(){
    ctx.clearRect(0,0,640,480);
    if(image&&mode==='uv'){const a=screen([0,0]);ctx.drawImage(image,a[0],a[1],scale,scale*aspect());}
    if(image&&mode!=='uv')for(const t of state.controls.triangles)texture(t);
    ctx.strokeStyle='#7cd8e8';ctx.lineWidth=.7;
    for(const t of state.controls.triangles){ctx.beginPath();t.forEach((i,n)=>n?ctx.lineTo(...screen(points()[i])):ctx.moveTo(...screen(points()[i])));ctx.closePath();ctx.stroke();}
    points().forEach((p,i)=>{ctx.beginPath();ctx.arc(...screen(p),i===state.selected?6:2.5,0,Math.PI*2);ctx.fillStyle=i===state.selected?'#ffcc55':'#d8f7ff';ctx.fill();});
  }
  canvas.onpointerdown=e=>{
    const p=mouse(e);let index=-1,distance=14;
    points().forEach((v,i)=>{const q=screen(v),d=Math.hypot(p[0]-q[0],p[1]-q[1]);if(d<distance){distance=d;index=i;}});
    drag={index,p,cx,cy};canvas.setPointerCapture(e.pointerId);if(index>=0){state.select(index);onEdit(false);}draw();
  };
  canvas.onpointermove=e=>{
    if(!drag)return;const p=mouse(e);
    if(drag.index<0){cx=drag.cx-(p[0]-drag.p[0])/scale;cy=drag.cy-(mode==='uv'?1:-1)*(p[1]-drag.p[1])/scale/aspect();}
    else {let q=world(p);if(mode==='uv')q=q.map(v=>Math.max(0,Math.min(1,v)));state.move(mode,drag.index,q);onEdit(true);}
    draw();
  };
  canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};
  canvas.onkeydown=e=>{
    const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,mode==='uv'?-1:1],ArrowDown:[0,mode==='uv'?1:-1]}[e.key];
    if(!direction)return;e.preventDefault();const step=(mode==='uv'?.001:1)*(e.shiftKey?10:1);
    let p=points()[state.selected].map((v,k)=>v+direction[k]*step);if(mode==='uv')p=p.map(v=>Math.max(0,Math.min(1,v)));
    state.move(mode,state.selected,p);onEdit(true);draw();
  };
  canvas.onwheel=e=>{e.preventDefault();const p=mouse(e),before=world(p);scale=Math.max(.01,Math.min(100000,scale*Math.exp(-e.deltaY*.001)));const after=world(p);cx+=before[0]-after[0];cy+=before[1]-after[1];draw();};
  fit();return {draw,fit,setImage(value){image=value;draw();},destroy(){image=null;canvas.onpointerdown=canvas.onpointermove=canvas.onpointerup=canvas.onpointercancel=canvas.onwheel=canvas.onkeydown=null;}};
}
