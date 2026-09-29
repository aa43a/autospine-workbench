export function existingBody({api,settings,openRun}){
  const panel=document.createElement('details'),title=document.createElement('summary');title.textContent='从已有身体候选继续制作';panel.append(title);
  const jobs=document.createElement('select'),versions=document.createElement('select');
  jobs.setAttribute('aria-label','已有身体动作');versions.setAttribute('aria-label','已有身体修复版本');
  const load=document.createElement('button'),start=document.createElement('button'),status=document.createElement('p');
  load.textContent='读取已有身体候选';start.textContent='接入制作链';start.disabled=true;
  panel.append(jobs,versions,load,start,status);document.getElementById('create').after(panel);
  let serial=0;
  async function select(){const version=++serial;start.disabled=true;versions.replaceChildren(new Option('原身体候选',''));if(!jobs.value)return;
    try{const result=await api(`/api/motions/${jobs.value}/view/related-candidates.json`);if(version!==serial)return;
      for(const [i,row] of result.rows.entries())versions.add(new Option(`已登记修复 ${i+1} · ${row.candidate_sha256.slice(0,10)}`,row.registration_sha256));
      start.disabled=false;status.textContent='保留现有身体与历史记录；重新构建联合动画、检查和交付，不继承阶段验收。';
    }catch(e){if(version===serial)status.textContent=e.message;}}
  jobs.onchange=select;
  load.onclick=async()=>{load.disabled=true;start.disabled=true;++serial;try{const result=await api('/api/motions');jobs.replaceChildren(new Option('选择已有身体动作',''));
    for(const job of result.jobs)if(job.kind==='adapt'&&job.status==='succeeded'&&!job.result?.joint_animation_profile&&!job.joint_parent_job_id)jobs.add(new Option(`${job.project_id} · ${job.name}`,job.job_id));
    status.textContent='请选择原身体或已完成的局部修复任务。';
  }catch(e){status.textContent=e.message;}finally{load.disabled=false;}};
  start.onclick=async()=>{start.disabled=true;try{const body={body_job_id:jobs.value,joint_config:settings().joint_config};if(versions.value)body.registration_sha256=versions.value;
    const result=await api('/api/production/from-body',body);await openRun(result.run_id);
  }catch(e){status.textContent=e.message;}finally{start.disabled=false;}};
}
