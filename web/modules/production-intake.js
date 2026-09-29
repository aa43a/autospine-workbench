import {validatePsdFile,importJobMessage} from './asset-import.js';
import {importRequest} from './motion-editor-intake.js';

export function createProductionIntake({refresh,selectProject,selectSource}){
  const $=id=>document.getElementById(id),key='autospine-production-intake-v1';
  let active=null,timer=null,busy=false;
  try{const saved=JSON.parse(localStorage.getItem(key));if(saved&&['psd','motion'].includes(saved.kind)&&/^(import|motion)-[a-f0-9]{32}$/.test(saved.id))active=saved;}catch{}
  function buttons(disabled){for(const id of ['psd-submit','motion-submit','generate-submit'])$(id).disabled=disabled;}
  async function request(url,options){const r=await fetch(url,options),value=await r.json();if(!r.ok)throw Error(value.reason_code||value.error||`请求失败 ${r.status}`);return value;}
  async function poll(){
    clearTimeout(timer);if(!active)return;
    try{
      const job=await request(active.kind==='psd'?`/api/asset-imports/${active.id}`:`/api/motions/${active.id}`);
      $('intake-status').textContent=active.kind==='psd'?importJobMessage(job):`${job.name||'动作'} · ${job.step||job.status}${job.reason_code?' · '+job.reason_code:''}`;
      const pending=['pending','running'].includes(job.status);buttons(pending);
      if(pending){timer=setTimeout(poll,2500);return;}
      if(job.status==='succeeded'){
        await refresh();if(active.kind==='psd')selectProject(job.project_id);else selectSource(job.job_id);
        $('intake-status').textContent+=' 已选入制作表单，可开始制作。';
      }
      active=null;localStorage.removeItem(key);
    }catch(e){$('intake-status').textContent=e.message;timer=setTimeout(poll,5000);}
  }
  async function submit(kind,url,options){
    if(busy||active)return;busy=true;buttons(true);$('intake-status').textContent='正在上传或提交…';
    try{const job=await request(url,options);active={kind,id:job.job_id};localStorage.setItem(key,JSON.stringify(active));await poll();}
    catch(e){$('intake-status').textContent=e.message;buttons(false);}finally{busy=false;}
  }
  $('psd-form').onsubmit=e=>{e.preventDefault();try{const file=$('psd-file').files[0];validatePsdFile(file);void submit('psd','/api/asset-imports',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Autospine-Intent':'pipeline-preview','X-Autospine-File-Name':encodeURIComponent(file.name)},body:file});}catch(error){$('intake-status').textContent=error.message;}};
  $('motion-form').onsubmit=e=>{e.preventDefault();try{void submit('motion','/api/motions',importRequest($('motion-file').files[0],'front',30));}catch(error){$('intake-status').textContent=error.message;}};
  $('generate-form').onsubmit=e=>{e.preventDefault();void submit('motion','/api/motions/generate',{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({prompt:$('prompt').value,duration_seconds:Number($('duration').value),seed:42,diffusion_steps:100,view:'front'})});};
  $('intake-refresh').onclick=poll;
  void poll();
}
