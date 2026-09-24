import {viewEditor} from './view-pose-editor.js';

export function validateViewHandoff(value, job, row, revision) {
  if(!value?.request||!value?.view_pose)throw Error('请选择包含 request 和 view_pose 的对应文件');
  const {request,view_pose:pose}=value;
  if(request.job_id!==job.job_id||request.draft_revision!==revision||
    request.artifact_sha256!==job.result.artifact_sha256||request.slot!==row.slot||request.animation!==row.animation||
    pose.slot!==row.slot||pose.animation!==row.animation||!request.view_needs?.length)throw Error('对应文件不属于当前新视角任务');
  if(!Array.isArray(pose.poses)||!pose.poses.length)throw Error('模板尚未填写目标姿态，请先编辑对应坐标和姿态时间');
  return {request,view_pose:pose};
}

export function viewReturn(parent,job,row) {
  const panel=document.createElement('fieldset');
  panel.innerHTML='<legend>新视角素材与姿态对应</legend><a download="view-pose-template.json">下载对应模板</a><p>这是高级回交入口：在模板中填写新贴图 UV、目标姿态坐标与时间，再选择 PNG。模板中的原坐标仅供参考，不是已修正结果。</p><label>已编辑的对应 JSON <input type="file" accept=".json" aria-label="新视角对应文件"></label><label>新视角 RGBA PNG <input type="file" accept="image/png" aria-label="新视角图片"></label><button type="button">提交新视角候选</button><p role="status">生成独立候选，保留原动画；切换边界与遮挡仍需检查。</p>';
  panel.style.cssText='min-width:0;width:100%;box-sizing:border-box;overflow-wrap:anywhere';
  for(const label of panel.querySelectorAll('label'))label.style.cssText='display:flex;flex-direction:column;gap:8px;margin:12px 0';
  for(const input of panel.querySelectorAll('input'))input.style.cssText='max-width:100%;min-width:0';
  parent.append(panel);
  const [jsonFile,pngFile]=panel.querySelectorAll('input'),button=panel.querySelector('button');
  const status=panel.querySelector('[role="status"]'),link=panel.querySelector('a');
  panel.querySelector('p').textContent='选择新视角 PNG 后，可在画布上编辑对应位置与姿态时间；也可上传已编辑的 JSON。源坐标仅作参考，保存姿态后才可回交候选。';
  const open=document.createElement('button');open.type='button';open.textContent='在画布上编辑新视角对应';panel.insertBefore(open,button);
  let current=null,generation=0,authored=null;
  const editor=viewEditor(panel,value=>{authored=value;jsonFile.value='';status.textContent='已加载画布姿态，使用当前所选 PNG 提交';},()=>{authored=null;status.textContent='画布已修改，请重新使用画布结果回交';});
  jsonFile.onchange=pngFile.onchange=()=>{generation++;open.disabled=false;authored=null;editor.reset();};
  open.onclick=async()=>{
    const revision=current,ticket=generation;open.disabled=true;
    try {
      const png=pngFile.files[0];if(!revision||!png)throw Error('请先选择新视角 PNG');
      if(png.size>8*1024*1024)throw Error('PNG 限 8 MB');
      const response=await fetch(link.href);const template=await response.json();
      if(!response.ok)throw Error(template.reason_code||'模板加载失败');
      const image=await createImageBitmap(png);
      if(ticket!==generation||png!==pngFile.files[0]){image.close();return;}
      authored=null;editor.load(template,image);status.textContent='请在画布调整并保存姿态，再使用画布结果回交';
    }catch(e){if(ticket===generation)status.textContent=e.message;}
    finally{if(ticket===generation)open.disabled=false;}
  };
  button.onclick=async()=>{
    const revision=current,ticket=generation;panel.disabled=true;
    try {
      const source=jsonFile.files[0],png=pngFile.files[0];
      if(!revision||(!source&&!authored)||!png)throw Error('请选择已编辑的对应文件和 PNG，或先保存画布结果');
      if(source?.size>8*1024*1024||png.size>8*1024*1024)throw Error('对应文件与 PNG 各限 8 MB');
      const body=validateViewHandoff(authored?structuredClone(authored):JSON.parse(await source.text()),job,row,revision);
      const bytes=await png.arrayBuffer();
      body.view_pose.texture_sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
      const bitmap=await createImageBitmap(png);
      body.view_pose.texture_size=[bitmap.width,bitmap.height];bitmap.close();
      body.png_base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('图片读取失败'));reader.readAsDataURL(png);});
      if(ticket!==generation)return;
      status.textContent='正在提交新视角候选…';
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view-pose-execute`,{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)});
      const result=await response.json();if(!response.ok)throw Error(result.reason_code||'提交失败');
      if(ticket!==generation)return;
      const progress=document.createElement('a');progress.href='/motions.html#'+encodeURIComponent(result.job_id);progress.textContent='查看构建进度与检查结果';
      status.replaceChildren(document.createTextNode('已创建独立候选。'),progress);
    }catch(error){if(ticket===generation)status.textContent=error.message;}
    finally{if(ticket===generation)panel.disabled=false;}
  };
  return revision=>{
    generation++;current=revision;authored=null;editor.reset();open.disabled=false;panel.disabled=false;panel.hidden=!revision;panel.style.display=revision?'':'none';
    link.href=revision?`/api/motions/${encodeURIComponent(job.job_id)}/view-pose-template/${revision}`:'';
    jsonFile.value='';pngFile.value='';
  };
}
