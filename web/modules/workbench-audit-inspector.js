export function createAuditInspector(document){
 const element=document.createElement('section'),title=document.createElement('p'),frame=document.createElement('iframe');
 frame.title='当前图层动作与骨骼检查';frame.style='width:100%;height:650px;border:1px solid #405466;border-radius:8px';
 const toggle=document.createElement('button');toggle.textContent='切换局部 / 整角色';toggle.type='button';toggle.className='button button-secondary';
 element.append(title,toggle,frame);element.hidden=true;
 let key='',message=null,isolated=true;
 function send(){if(message)frame.contentWindow?.postMessage({...message,isolated},globalThis.location?.origin);}
 toggle.onclick=()=>{isolated=!isolated;send();};
 const ready=e=>{if(e.source===frame.contentWindow&&e.origin===globalThis.location?.origin&&e.data?.type==='audit-player-ready')send();};
 globalThis.addEventListener?.('message',ready);
 return {element,show(job,row){
  element.hidden=false;title.textContent=`检查 ${row.name} · 策略目标 ${row.option_id} · 可播放动作、拖动时间轴并切换整角色对照`;
  const next=`${job.project_id}/${job.job_id}/${job.artifact_sha256}`;
  message={type:'audit-focus',artifact:job.artifact_sha256,regions:job.layers?.find(l=>l.layer_id===row.layer_id)?.regions?.map(r=>r.region_id)||[row.layer_id],bone:row.option_id?.replace(/^rigid:/,'')};
  if(next!==key){key=next;frame.src=`/api/projects/${encodeURIComponent(job.project_id)}/automation/character/jobs/${encodeURIComponent(job.job_id)}/view/player.html?audit=1`;}
  send();
 },clear(){key='';message=null;element.hidden=true;frame.src='about:blank';},dispose(){globalThis.removeEventListener?.('message',ready);frame.src='about:blank';}};
}
