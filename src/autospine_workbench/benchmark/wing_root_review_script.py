"""Local draft controls and nested SVG transforms; not a Spine Runtime."""
SCRIPT=r'''
function wingPoint(point,root,anchor,localAngle,chestAngle){
 const rotate=(p,c,degrees)=>{const a=degrees*Math.PI/180,dx=p[0]-c[0],dy=p[1]-c[1];
  return [c[0]+dx*Math.cos(a)-dy*Math.sin(a),c[1]+dx*Math.sin(a)+dy*Math.cos(a)];};
 return rotate(rotate(point,root,localAngle),anchor,chestAngle);
}
function validateWingDraft(roots,base,doc){
 const keys=(a,b)=>a&&typeof a==='object'&&!Array.isArray(a)&&JSON.stringify(Object.keys(a).sort())===JSON.stringify(Object.keys(b).sort());
 if(!keys(doc,base)||doc.schema!==base.schema||doc.source_roots_sha256!==base.source_roots_sha256||
    doc.authority!=='none'||doc.production_authorized!==false||!Array.isArray(doc.records)||doc.records.length!==base.records.length)throw Error('草稿来源或版本不匹配');
 doc.records.forEach((r,i)=>{const b=base.records[i];
  if(!keys(r,b)||!Number.isInteger(r.relation_index)||!Number.isInteger(r.component_id)||r.relation_index!==b.relation_index||r.component_id!==b.component_id)throw Error('组件清单不匹配');
  const c=roots.rows[r.relation_index].components.find(v=>v.component_id===r.component_id);
  if(r.root_index!==null&&(!Number.isInteger(r.root_index)||r.root_index<0||r.root_index>=c.roots.length))throw Error('未知根部候选');
 });return structuredClone(doc);
}
if(typeof document!=='undefined'){
 const {roots,draft:base}=JSON.parse(document.getElementById('state').textContent);
 let current=structuredClone(base),history=[];
 const fields=[...document.querySelectorAll('select[data-record]')],status=document.getElementById('status');
 const stage=document.getElementById('stage'),wings=document.getElementById('wings');
 const chest=document.getElementById('chest-angle'),flap=document.getElementById('flap-angle');
 const anchor=roots.rows[0].anchor_xy;
 function show(){
  const ca=Number(chest.value),fa=Number(flap.value);
  stage.setAttribute('transform',`rotate(${ca} ${anchor[0]} ${anchor[1]})`);
  current.records.forEach((r,i)=>{
   fields[i].value=r.root_index===null?'':String(r.root_index);
   const c=roots.rows[r.relation_index].components.find(v=>v.component_id===r.component_id);
   const part=document.querySelector(`[data-wing="${r.component_id}"]`),marker=document.querySelector(`[data-root-marker="${r.component_id}"]`);
   if(!part)return;
   const root=r.root_index===null?null:c.roots[r.root_index].source_xy;
   part.setAttribute('transform',root?`rotate(${fa} ${root[0]} ${root[1]})`:'');
   marker.style.display=root?'':'none';
   if(root){marker.setAttribute('cx',root[0]);marker.setAttribute('cy',root[1]);}
  });
  status.textContent=`已选择 ${current.records.filter(r=>r.root_index!==null).length} 个组件；胸骨 ${ca}°，局部 ${fa}°。仅预览草稿，未授权生产。`;
 }
 function remember(){history.push(structuredClone(current));if(history.length>100)history.shift();}
 fields.forEach((field,i)=>field.onchange=()=>{remember();current.records[i].root_index=field.value===''?null:Number(field.value);show();});
 chest.oninput=flap.oninput=show;
 document.getElementById('front').onchange=e=>{if(e.target.checked)stage.append(wings);else stage.prepend(wings);};
 document.getElementById('undo').onclick=()=>{if(history.length){current=history.pop();show();}};
 document.getElementById('reset-pose').onclick=()=>{chest.value=0;flap.value=0;show();};
 document.getElementById('save').onclick=()=>{try{
  const data=validateWingDraft(roots,base,current),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='wing-root-draft-v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){status.textContent=e.message;}};
 document.getElementById('load').onchange=async e=>{try{
  const file=e.target.files[0];if(!file)return;if(file.size>1024*1024)throw Error('文件过大');
  const data=validateWingDraft(roots,base,JSON.parse(await file.text()));remember();current=data;show();
 }catch(error){status.textContent=error.message;}e.target.value='';};
 show();
}
'''
