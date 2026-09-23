export function materialReturn(parent, job) {
  const panel=document.createElement('fieldset');
  panel.innerHTML='<legend>回交姿态素材</legend><label>任务包内 request.json <input type="file" accept=".json" aria-label="素材任务身份文件"></label><label>修改后的同画布 RGBA PNG <input type="file" accept="image/png" aria-label="回交姿态图片"></label><button type="button">保存回交素材</button><p role="status">保存后等待区域映射与重建，不直接替换当前动画。</p>';
  panel.style.cssText='min-width:0;width:100%;box-sizing:border-box;grid-column:1/-1;overflow-wrap:anywhere';
  for(const label of panel.querySelectorAll('label'))label.style.cssText='display:flex;flex-direction:column;align-items:stretch;gap:8px;min-width:0;width:100%;margin-bottom:12px';
  for(const input of panel.querySelectorAll('input'))input.style.cssText='min-width:0;width:100%;max-width:100%;box-sizing:border-box';
  parent.append(panel);const [requestFile,pngFile]=panel.querySelectorAll('input'),button=panel.querySelector('button'),status=panel.querySelector('p');
  let current=null;
  const refresh=document.createElement('button');refresh.type='button';refresh.textContent='查看已回交版本';panel.append(refresh);
  refresh.onclick=async()=>{
    const revision=current;refresh.disabled=true;
    try{
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/material-return`,{cache:'no-store'});
      const value=await response.json();if(!response.ok)throw Error(value.reason_code||'读取失败');
      if(current!==revision)return;
      const rows=value.returns.filter(r=>r.draft_revision===revision);
      status.textContent=rows.length?`当前草稿已有 ${rows.length} 个回交版本，均等待映射与重建。`:'当前草稿尚无回交版本。';
    }catch(e){status.textContent=e.message;}finally{refresh.disabled=false;}
  };
  button.onclick=async()=>{
    const revision=current;panel.disabled=true;
    try {
      const req=requestFile.files[0],png=pngFile.files[0];
      if(!revision||!req||!png)throw Error('请选择任务身份文件和修改后的 PNG');
      if(req.size>128*1024||png.size>8*1024*1024)throw Error('身份文件限 128 KB，PNG 限 8 MB');
      const request=JSON.parse(await req.text());
      if(request.draft_revision!==revision||request.job_id!==job.job_id)throw Error('任务文件不属于当前处理草稿');
      const encoded=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(Error('图片读取失败'));r.readAsDataURL(png);});
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/material-return`,{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({request,png_base64:encoded})});
      const value=await response.json();if(!response.ok)throw Error(value.reason_code||'回交失败');
      status.textContent=value.unchanged_source?'已保存；图片与原纹理相同，尚未提供修改。':'已保存独立素材版本；尚未映射或替换动画。';
    }catch(e){status.textContent=e.message;}finally{panel.disabled=false;}
  };
  return revision=>{current=revision;panel.hidden=!revision;panel.style.display=revision?'':'none';};
}
