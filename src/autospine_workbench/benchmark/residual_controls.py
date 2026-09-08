"""Whole-draft restore/save and undo; suggestions are never preselected."""
SCRIPT=r'''
function validateResidualDraft(base,doc){
  const sameKeys=(a,b)=>a&&typeof a==='object'&&!Array.isArray(a)&&JSON.stringify(Object.keys(a).sort())===JSON.stringify(Object.keys(b).sort());
  if(!sameKeys(doc,base)||doc.schema!==base.schema||doc.authority!=='none'||doc.production_authorized!==false||
     doc.source_partitions_sha256!==base.source_partitions_sha256||!Array.isArray(doc.records)||doc.records.length!==base.records.length)throw Error('草稿来源或结构不匹配');
  doc.records.forEach((r,i)=>{if(!sameKeys(r,base.records[i])||r.layer_id!==base.records[i].layer_id||
    !['pending','retain','nearest_4px'].includes(r.policy)||typeof r.notes!=='string'||Array.from(r.notes).length>2000||
    /\p{C}/u.test(r.notes.replace(/[\n\r\t]/g,''))||(r.policy!=='pending'&&!r.notes.trim()))throw Error('请选择规则并填写说明');});
  return structuredClone(doc);
}
if(typeof document!=='undefined'){
  const base=JSON.parse(document.getElementById('draft').textContent);let current=structuredClone(base),history=[];
  const cards=[...document.querySelectorAll('article')],status=document.getElementById('status');
  function show(){cards.forEach((c,i)=>{c.querySelector('select').value=current.records[i].policy;c.querySelector('textarea').value=current.records[i].notes;});
    status.textContent=`${current.records.filter(r=>r.policy==='pending').length}/${current.records.length} 项待复核；页面右侧始终是试算候选，保存草稿不授予绑定权。`;}
  const remember=()=>{history.push(structuredClone(current));if(history.length>100)history.shift();};
  cards.forEach((c,i)=>c.addEventListener('change',()=>{remember();current.records[i].policy=c.querySelector('select').value;current.records[i].notes=c.querySelector('textarea').value;show();}));
  document.getElementById('undo').onclick=()=>{if(history.length){current=history.pop();show();}};
  document.getElementById('save').onclick=()=>{try{const doc=validateResidualDraft(base,current),url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='residual-draft-v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='草稿已下载。';}catch(e){status.textContent=e.message;}};
  document.getElementById('load').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>2*1024*1024)throw Error('文件过大');
    const restored=validateResidualDraft(base,JSON.parse(await f.text()));remember();current=restored;show();}catch(error){status.textContent=error.message;}e.target.value='';};show();
}
'''
