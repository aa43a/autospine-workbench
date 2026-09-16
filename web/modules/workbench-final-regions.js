export function createFinalRegionReview(document, save, {afterComponents=false}={}) {
  const element=document.createElement('details'),title=document.createElement('summary'),body=document.createElement('div');
  title.textContent=afterComponents?'拆分后残余排除（已检查后选择）':'最终残余排除（已检查后选择）';element.append(title,body);
  let identity=null,selected=new Set();
  return {element,sync(job,value,disabled){
    const key=job?.artifact_sha256||null;
    if(identity!==key){identity=key;selected=new Set();}
    body.replaceChildren();
    element.hidden=false;
    const text=document.createElement('p');
    text.textContent=afterComponents?'移除拆分后新产生的静态残余；不改变已有排除与部件绑定，保存后需要重建。':'只移除明确确认的静态残余，在动作和纹理修复之后执行；保存后需要重建。';body.append(text);
    if(value?.active){
      text.textContent=`已保存 ${value.review.decisions.length} 处最终排除，重建时自动应用。来源不一致将阻塞。`;
      const undo=document.createElement('button');undo.type='button';undo.textContent='撤销最终排除';undo.disabled=disabled;
      undo.onclick=()=>save({action:'revoke'});body.append(undo);
    }
    const rows=(job?.layers||[]).flatMap(l=>(l.regions||[]).filter(r=>r.state==='static_reference'&&r.region_id.includes('residual')).map(r=>({layer_id:l.layer_id,region_id:r.region_id})));
    const button=document.createElement('button');button.type='button';button.textContent=value?.active?'追加所选残余，保留已确认项':'保存所选残余排除';
    for(const row of rows){
      const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';
      check.checked=selected.has(row.region_id);check.disabled=disabled;
      check.onchange=()=>{check.checked?selected.add(row.region_id):selected.delete(row.region_id);button.disabled=disabled||!selected.size;};
      const name=document.createElement('span');name.textContent=row.region_id;
      label.append(check,name);body.append(label,document.createElement('br'));
    }
    button.disabled=disabled||!selected.size;
    button.onclick=()=>save({action:value?.active?'append':'replace',job_id:job.job_id,expected_artifact_sha256:job.artifact_sha256,regions:rows.filter(r=>selected.has(r.region_id))});
    body.append(button);element.hidden=Boolean((!rows.length&&!value?.active)||(afterComponents&&!job?.component_mounts&&!value?.active)||(!afterComponents&&job?.component_mounts&&!value?.active));
  }};
}
