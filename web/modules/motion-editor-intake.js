// Use the existing immutable source jobs; loading a result remains an explicit edit.
import {successorId} from './motion-job-actions.js';
export const canRetrySource=job=>[undefined,'import','generate'].includes(job?.kind)&&['failed','cancelled','interrupted'].includes(job?.status);
export function importRequest(file, view, fps) {
  if (!file || file.size < 16 || file.size > 64 * 1024 * 1024) throw Error('请选择 16 字节至 64 MB 的动作文件');
  if (!/\.(fbx|bvh|npz)$/i.test(file.name)) throw Error('支持 FBX、BVH 或 Kimodo SOMA77 NPZ');
  const headers = {'Content-Type':'application/octet-stream','X-Autospine-Intent':'pipeline-preview',
    'X-Autospine-File-Name':encodeURIComponent(file.name),'X-Autospine-Motion-View':view};
  if (/\.npz$/i.test(file.name)) {
    if (!Number.isFinite(Number(fps)) || Number(fps)<1 || Number(fps)>240) throw Error('NPZ 帧率须为 1–240');
    headers['X-Autospine-Npz-Profile']='kimodo-soma77-v1';headers['X-Autospine-Npz-Fps']=String(fps);
  }
  return {method:'POST',headers,body:file};
}
export function createEditorIntake({refresh,load}) {
  const $=id=>document.getElementById(id),storage='autospine-motion-editor-source-job-v1';
  let id=null,timer=null,busy=false,suspended=false,configured=false,job=null;
  try {id=localStorage.getItem(storage);} catch {}
  if (id&&!/^motion-[a-f0-9]{32}$/.test(id)) id=null;
  async function request(url,options) {
    const response=await fetch(url,options),value=await response.json();
    if(!response.ok)throw Error(value.message||value.error||`请求失败 (${response.status})`);
    return value;
  }
  const active=()=>job&&['pending','queued','running','cancelling'].includes(job.status);
  function controls() {
    $('intake-import').disabled=busy||!!active();$('intake-generate').disabled=busy||!!active()||!configured;
    $('intake-cancel').disabled=busy||!active();
    $('intake-retry').disabled=busy||!canRetrySource(job);
    $('intake-load').disabled=busy||job?.status!=='succeeded'||job?.result?.motion_status!=='compiled';
  }
  const stages={queued:'等待执行',generate_motion:'生成动作（含模型加载）',verify_generation:'检查生成结果',
    parse:'解析动作',compile:'转换动作',complete:'完成',failed:'失败',cancelled:'已取消'};
  async function poll() {
    clearTimeout(timer);if(!id||suspended)return;
    const requested=id;
    try {
      const value=await request(`/api/motions/${requested}`);
      if(id!==requested||suspended)return;job=value;
      $('intake-status').textContent=`${job.name} · ${stages[job.step]||job.step||job.status}${job.error?' · '+JSON.stringify(job.error):''}`;
      if(job.status==='succeeded')$('intake-status').textContent+='。点击“载入编辑”替换当前源动作；角度轨道将重置。';
      $('intake-record').href=`/motions.html#${id}`;$('intake-record').hidden=false;controls();
      if(active()&&!suspended)timer=setTimeout(poll,2500);
    } catch(e) {if(id!==requested||suspended)return;$('intake-status').textContent=e.message;timer=setTimeout(poll,5000);}
  }
  async function submit(url,options,original=null) {
    if(busy||active())return;busy=true;controls();$('intake-status').textContent='正在提交…';
    try {const value=await request(url,options);id=original?successorId(original,value):value.job_id;job=value;
      try{localStorage.setItem(storage,id);}catch{} await poll();
    }catch(e){$('intake-status').textContent=e.message;}finally{busy=false;controls();}
  }
  $('intake-import-form').onsubmit=event=>{
    event.preventDefault();try{void submit('/api/motions',importRequest($('intake-file').files[0],$('intake-view').value,$('intake-fps').value));}
    catch(e){$('intake-status').textContent=e.message;}
  };
  $('intake-generation-form').onsubmit=event=>{
    event.preventDefault();if(!configured)return;
    void submit('/api/motions/generate',{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},
      body:JSON.stringify({prompt:$('intake-prompt').value,duration_seconds:Number($('intake-duration').value),
        seed:Number($('intake-seed').value),diffusion_steps:Number($('intake-steps').value),view:$('intake-view').value})});
  };
  $('intake-cancel').onclick=async()=>{
    if(busy||!active())return;busy=true;controls();
    try{await request(`/api/motions/${id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:'{}'});await poll();}
    catch(e){$('intake-status').textContent=e.message;}finally{busy=false;controls();}
  };
  $('intake-load').onclick=async()=>{
    if(busy||job?.result?.motion_status!=='compiled')return;busy=true;controls();
    try{await refresh();await load(id);}catch(e){$('intake-status').textContent=e.message;}finally{busy=false;controls();}
  };
  $('intake-retry').onclick=()=>{
    if(busy||!canRetrySource(job))return;
    void submit(`/api/motions/${id}/retry`,{method:'POST',headers:{'Content-Type':'application/json',
      'X-Autospine-Intent':'pipeline-preview'},body:'{}'},id);
  };
  $('intake-refresh').onclick=()=>void poll();
  addEventListener('pagehide',()=>{suspended=true;clearTimeout(timer);});
  addEventListener('pageshow',()=>{suspended=false;void poll();});
  controls();void poll();
  return {update(value){configured=value.kimodo_generation==='configured';
    $('intake-environment').textContent=configured?'本地 Kimodo 已配置，执行时检查模型与 GPU。':'Kimodo 未配置，可先导入动作文件。';controls();}};
}
