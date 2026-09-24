const el=id=>document.getElementById(id);
try {
 const {createGeometryMetrics}=await import('./pose-geometry-metrics.js');
 const read=async name=>{const r=await fetch(name);if(!r.ok)throw Error(`读取 ${name} 失败`);return r.json();};
 const [scene,config]=await Promise.all([read('scene.json'),read('editor-config.json')]);
 let sourceReference=null;
 const {slot,animation,vertices,interval}=config.request,doc=scene.skeleton;
 if(scene.artifact_sha256!==config.artifact)throw Error('候选版本不匹配');
 const canvas=document.querySelector('canvas'),{width,height,left,bottom}=scene.info;
 canvas.width=width;canvas.height=height;
 const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false});if(!gl)throw Error('WebGL 不可用');
 const atlas=new spine.TextureAtlas(scene.atlas);
 await Promise.all(atlas.pages.map(async p=>{const i=new Image();i.src=scene.textures[p.name];await i.decode();p.setTexture(new spine.GLTexture(gl,i,false,false));}));
 const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);
 const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);
 renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
 let view={width,height,left,bottom};
 const mesh=doc.skins[0].attachments[slot][slot],owners=[];let cursor=0,size=0;
 while(cursor<mesh.vertices.length){const count=mesh.vertices[cursor++],row=[];
  for(let i=0;i<count;i++){row.push({bone:mesh.vertices[cursor],offset:size});size+=2;cursor+=4;}owners.push(row);}
 const selected=new Set(vertices),triangles=[];
 for(let i=0;i<mesh.triangles.length;i+=3)triangles.push(mesh.triangles.slice(i,i+3));
 let time=interval[0],playing=false,previous=0,poses=[],history=[],drag=null,lastWorld=[],cached=[],storageError='';
 const entryTime=new URL(location.href).searchParams.get('time');
 if(entryTime!==null&&entryTime.trim()!==''&&Number.isFinite(Number(entryTime))&&Number(entryTime)>=interval[0]&&Number(entryTime)<=interval[1])time=Number(entryTime);
 const legacyKey=`pose-geometry-v1:${config.request.document_sha256}:${slot}:${animation}`;
 const storageKey=`${legacyKey}:${vertices.join(',')}:${interval.join(',')}`;
 function skeleton(t,setup=false){const s=new spine.Skeleton(data);s.setupPose();if(!setup){const state=new spine.AnimationState(new spine.AnimationStateData(data));state.setAnimation(0,animation,false);state.update(t);state.apply(s);}s.updateWorldTransform(spine.Physics.update);return s;}
 function points(s){const sl=s.findSlot(slot),a=sl.appliedPose.attachment;if(!a?.bones)throw Error('需要当前加权 Mesh');const v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(s,sl,0,v.length,v,0,2);return Array.from({length:v.length/2},(_,i)=>[v[i*2],v[i*2+1]]);}
 const setup=points(skeleton(0,true)),measure=createGeometryMetrics(setup,triangles);
 function offsets(pose){const s=skeleton(pose.time),base=points(s),out=Array(size).fill(0);
  vertices.forEach((v,i)=>{const dx=pose.points[i][0]-base[v][0],dy=pose.points[i][1]-base[v][1];
   for(const o of owners[v]){const b=s.bones[o.bone].appliedPose,det=b.a*b.d-b.b*b.c;if(Math.abs(det)<1e-10)throw Error('骨骼变换退化');out[o.offset]=(b.d*dx-b.b*dy)/det;out[o.offset+1]=(b.a*dy-b.c*dx)/det;}});return out;}
 function rebuild(){cached=[{time:interval[0],values:Array(size).fill(0)},...poses.map(p=>({time:p.time,values:offsets(p)})),{time:interval[1],values:Array(size).fill(0)}];}
 function correction(t){if(t<=interval[0]||t>=interval[1])return Array(size).fill(0);let i=0;while(i+1<cached.length&&cached[i+1].time<=t)i++;const a=cached[i],b=cached[i+1],f=(t-a.time)/(b.time-a.time);return a.values.map((x,j)=>x+(b.values[j]-x)*f);}
 function draw(){const s=skeleton(time),sl=s.findSlot(slot),originalQuality=measure(points(s));
  if(el('preview').checked){const extra=correction(time),d=sl.appliedPose.deform;if(!d.length)for(let i=0;i<size;i++)d.push(0);for(let i=0;i<size;i++)d[i]+=extra[i];}
  lastWorld=points(s);
  const quality=measure(lastWorld);
  if(el('isolate').checked)for(const x of s.slots)if(x.data.name!==slot)x.appliedPose.setAttachment(null);
  renderer.camera.setViewport(view.width,view.height);renderer.camera.position.x=view.left+view.width/2;renderer.camera.position.y=view.bottom+view.height/2;renderer.camera.update();
  gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);renderer.begin();renderer.drawSkeleton(s);
  if(el('overlay').checked){for(const tri of triangles)if(tri.some(v=>selected.has(v)))for(let i=0;i<3;i++)renderer.line(...lastWorld[tri[i]],...lastWorld[tri[(i+1)%3]],{r:1,g:.85,b:.2,a:.6});
   for(const v of vertices){const [x,y]=lastWorld[v],r=3*view.width/canvas.getBoundingClientRect().width;renderer.line(x-r,y,x+r,y,{r:1,g:1,b:0,a:1});renderer.line(x,y-r,x,y+r,{r:1,g:1,b:0,a:1});}}
  if(el('failures').checked){
   for(const index of quality.badTriangles){const tri=triangles[index];for(let i=0;i<3;i++)renderer.line(...lastWorld[tri[i]],...lastWorld[tri[(i+1)%3]],{r:1,g:.15,b:.2,a:1});}
   for(const edge of quality.badEdges)renderer.line(...lastWorld[edge[0]],...lastWorld[edge[1]],{r:1,g:.2,b:1,a:1});
  }
  renderer.end();el('time').value=time;el('position').textContent=`${time.toFixed(3)} / ${interval[1].toFixed(3)} 秒`;
  const describe=q=>`翻转 ${q.inversions}，面积超限 ${q.badTriangles.length}，拉伸超限 ${q.badEdges.length}，最大边长 ${q.maxEdgeStretch.toFixed(3)} 倍`;
  const outside=quality.badTriangles.filter(i=>!triangles[i].some(v=>selected.has(v))).length;
  el('quality').textContent=`当前部件原候选：${describe(originalQuality)}。显示结果：${describe(quality)}。${outside} 个面积异常位于编辑范围外。接缝、轮廓与整段尚未验收。`;
  window.poseGeometryEditorState={time,poses:structuredClone(poses),points:lastWorld,view:{...view},artifact:config.artifact,quality,originalQuality};
  sourceReference?.seek(time);
 }
 function request(){return {...config.request,poses:structuredClone(poses)};}
 function persist(){try{localStorage.setItem(storageKey,JSON.stringify(request()));storageError='';}catch{storageError='本地保存失败，请立即导出草稿。';}}
 function refresh(){el('keys').replaceChildren(...poses.map(p=>{const o=document.createElement('option');o.value=p.time;o.textContent=`${p.time.toFixed(6)} 秒`;return o;}));el('remove').disabled=!poses.length;el('download').disabled=!poses.length;el('undo').disabled=!history.length;el('status').textContent=storageError||`已保存 ${poses.length} 个关键姿态；仅本地草稿，尚未构建。`;}
 function snapshot(){history.push(structuredClone(poses));if(history.length>50)history.shift();}
 function validate(r){for(const k of ['document_sha256','mesh_sha256','animation','slot'])if(r[k]!==config.request[k])throw Error('草稿来源版本不匹配');
  if(JSON.stringify(r.vertices)!==JSON.stringify(vertices)||JSON.stringify(r.interval)!==JSON.stringify(interval))throw Error('草稿区域或区间不匹配');
  if(!Array.isArray(r.poses)||r.poses.length>512)throw Error('姿态数量无效');let previous=interval[0];
  for(const p of r.poses){if(!Number.isFinite(p.time)||p.time<=previous||p.time>=interval[1]||!Array.isArray(p.points)||p.points.length!==vertices.length||!p.points.every(x=>Array.isArray(x)&&x.length===2&&x.every(Number.isFinite)))throw Error('姿态数据无效');previous=p.time;}return structuredClone(r.poses);}
 function stop(){playing=false;el('play').textContent='播放';}
 function mouse(e){const r=canvas.getBoundingClientRect();return [view.left+(e.clientX-r.left)/r.width*view.width,view.bottom+view.height-(e.clientY-r.top)/r.height*view.height];}
 canvas.onpointerdown=e=>{stop();if(!el('preview').checked||!el('overlay').checked||time<=interval[0]||time>=interval[1]){el('status').textContent='请打开补丁及网格显示，并选择区间内部时间。';return;}
  const p=mouse(e),r=canvas.getBoundingClientRect(),near=vertices.map(v=>({v,d:Math.hypot((lastWorld[v][0]-p[0])*r.width/view.width,(lastWorld[v][1]-p[1])*r.height/view.height)})).sort((a,b)=>a.d-b.d)[0];if(near.d>12)return;
  if(poses.length>=512&&!poses.some(x=>x.time===time)){el('status').textContent='已达 512 个姿态上限';return;}
  snapshot();drag={id:e.pointerId,v:near.v,time,points:vertices.map(v=>[...lastWorld[v]])};canvas.setPointerCapture(e.pointerId);};
 canvas.onpointermove=e=>{if(!drag||drag.id!==e.pointerId)return;drag.points[vertices.indexOf(drag.v)]=mouse(e);poses=poses.filter(p=>p.time!==drag.time);poses.push({time:drag.time,points:structuredClone(drag.points)});poses.sort((a,b)=>a.time-b.time);rebuild();draw();};
 function finish(){if(!drag)return;drag=null;persist();refresh();}
 canvas.onpointerup=finish;canvas.onpointercancel=()=>{if(drag){poses=history.pop();drag=null;rebuild();draw();refresh();}};
 el('time').oninput=()=>{finish();stop();time=Number(el('time').value);draw();};
 el('play').onclick=()=>{finish();playing=!playing;previous=performance.now();if(playing&&time>=interval[1])time=interval[0];el('play').textContent=playing?'暂停':'播放';};
 el('keys').onchange=()=>{finish();stop();time=Number(el('keys').value);draw();};
 el('undo').onclick=()=>{stop();if(history.length){poses=history.pop();rebuild();persist();refresh();draw();}};
 el('remove').onclick=()=>{if(!el('keys').value)return;snapshot();poses=poses.filter(p=>p.time!==Number(el('keys').value));rebuild();persist();refresh();draw();};
 for(const id of ['isolate','overlay','preview','failures'])el(id).onchange=()=>{finish();draw();};
 el('focus').onclick=()=>{finish();const p=vertices.map(v=>lastWorld[v]),xs=p.map(p=>p[0]),ys=p.map(p=>p[1]);
  const l=Math.min(...xs),r=Math.max(...xs),b=Math.min(...ys),t=Math.max(...ys),h=Math.max(50,(t-b)*1.3,(r-l)*1.3*height/width),w=h*width/height;
  view={width:w,height:h,left:(l+r-w)/2,bottom:(b+t-h)/2};draw();};
 el('full').onclick=()=>{finish();view={width,height,left,bottom};draw();};
 el('download').onclick=()=>{finish();const url=URL.createObjectURL(new Blob([JSON.stringify(request(),null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`pose-geometry-${slot}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 el('import').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('草稿超过 8MB');const restored=validate(JSON.parse(await file.text()));stop();snapshot();poses=restored;rebuild();persist();refresh();draw();}catch(error){el('status').textContent=error.message;}};
 try{const saved=localStorage.getItem(storageKey)||localStorage.getItem(legacyKey);if(saved)poses=validate(JSON.parse(saved));}catch(error){storageError=`本地草稿未恢复：${error.message}`;}
 rebuild();refresh();el('time').max=interval[1];el('time').min=interval[0];for(const id of ['time','play','import'])el(id).disabled=false;
 el('identity').textContent=`${slot} · ${animation} · 候选 ${config.artifact}`;draw();
 if(config.source_comparison_url){
  import('./pose-source.js').then(module=>module.loadSourceReference(config)).then(reference=>{sourceReference=reference;sourceReference.seek(time);})
   .catch(error=>{el('source-error').textContent=`源动作参考不可用：${error.message}。未替换为其他来源；当前草稿仍可编辑。`;});
 }
 if(config.execute_url){
  const endpoint=new URL(config.execute_url,location.href);
  if(endpoint.origin!==location.origin)throw Error('构建地址必须同源');
  el('build').hidden=false;el('build').disabled=false;
  el('build').onclick=async()=>{finish();stop();el('build').disabled=true;
   try{if(!poses.length)throw Error('请先拖动顶点保存一个姿态');
    el('build-status').textContent='正在保存并提交独立候选…';
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({artifact_sha256:config.artifact,pose_geometry:request()})});
    const result=await response.json();if(!response.ok)throw Error(result.reason_code||'构建提交失败');
    const link=document.createElement('a');link.textContent='查看任务进度与候选结果';link.href='/motions.html#'+encodeURIComponent(result.job_id);link.target='_top';
    el('build-status').replaceChildren(document.createTextNode('修改已封存到独立任务；原候选保留。'),link);
   }catch(error){el('build-status').textContent=error.message;}finally{el('build').disabled=false;}
  };
 }
 function tick(now){if(playing){time+=Math.max(0,now-previous)/1000;if(time>=interval[1]){time=interval[1];stop();}draw();}previous=now;requestAnimationFrame(tick);}requestAnimationFrame(tick);
 document.addEventListener('visibilitychange',()=>{if(document.hidden){finish();stop();}});
 window.poseGeometryEditorReady=true;
}catch(error){el('status').textContent=`编辑器不可用：${error.message}`;window.poseGeometryEditorError=String(error);}
