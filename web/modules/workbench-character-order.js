"use strict";

export function createCharacterOrder(document, save) {
  const make=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=make('details'),body=make('div');
  element.append(make('summary','部件前后遮挡'),body);
  let identity=null,pairs=[];
  return {element,sync(job,state,disabled){
    const key=job?.artifact_sha256||null;
    if(key!==identity){identity=key;pairs=[];}
    body.replaceChildren();
    if(state?.active){
      body.append(make('p','已保存遮挡关系。重建后生效，新的动作或部件来源需要重新核对。'));
      for(const [back,front] of state.review.constraints)body.append(make('p',`${front} 在 ${back} 前面`));
      const undo=make('button','撤销遮挡关系');undo.type='button';undo.disabled=disabled;
      undo.onclick=()=>save({action:'revoke'});body.append(undo);return;
    }
    body.append(make('p','只调整绘制顺序，不修改绑定。先查看 Runtime 对照，再添加需要遮挡的部件关系；保存后重建并检查完整动作。'));
    const rows=(job?.layers||[]).flatMap(l=>(l.regions||[]).map((r,i)=>({id:r.region_id,label:`${l.name||l.layer_id}${l.regions.length>1?' · 区域 '+(i+1):''}`})));
    const back=make('select'),front=make('select');back.setAttribute('aria-label','后方部件');front.setAttribute('aria-label','前方部件');
    for(const select of [back,front]){
      const placeholder=make('option','请选择部件');placeholder.value='';select.append(placeholder);
      for(const row of rows){const o=make('option',row.label);o.value=row.id;select.append(o);}
      select.disabled=disabled||!key;
    }
    const list=make('div'),add=make('button','添加遮挡关系'),commit=make('button','确认并保存遮挡关系');
    add.type=commit.type='button';add.disabled=true;
    const renderPairs=()=>{list.replaceChildren();for(const [i,pair] of pairs.entries()){
      const text=make('p',`${rows.find(r=>r.id===pair[1])?.label} 在 ${rows.find(r=>r.id===pair[0])?.label} 前面 `);
      const remove=make('button','移除');remove.type='button';remove.disabled=disabled;remove.onclick=()=>{pairs.splice(i,1);renderPairs();};text.append(remove);list.append(text);
    }commit.disabled=disabled||!key||!pairs.length;};
    const select=()=>{add.disabled=disabled||!back.value||!front.value||back.value===front.value;};
    back.onchange=front.onchange=select;
    add.onclick=()=>{if(!pairs.some(p=>p[0]===back.value&&p[1]===front.value))pairs.push([back.value,front.value]);renderPairs();};
    commit.onclick=()=>save({action:'replace',job_id:job.job_id,expected_artifact_sha256:job.artifact_sha256,constraints:pairs.map(p=>[...p])});
    body.append(make('label','后方 '),back,make('label','前方 '),front,add,list,commit);renderPairs();
  }};
}
