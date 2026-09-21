import {createCohortSync} from './motion-cohort-sync.js';

export function createExperimentPanel(container, request) {
  let revision=0, sync=null, time=0, end=null;
  function clear(){revision++;sync?.clear();sync=null;container.replaceChildren();}
  async function load(job){
    clear();const token=revision;
    try{
      const base=`/api/motions/${job}/view`, report=await request(base+'/experiments.json');
      if(token!==revision||!report.rows.length)return;
      const title=document.createElement('h2');title.textContent='局部修正实验对照';container.append(title);
      const select=document.createElement('select');select.setAttribute('aria-label','局部修正实验');
      select.add(new Option('选择实验，不改变当前候选',''));
      for(const row of report.rows)select.add(new Option(`${row.correction_profile} · ${row.candidate_bundle_sha256.slice(0,10)}`,row.evidence_sha256));
      const body=document.createElement('section');container.append(select,body);
      select.onchange=()=>{
        sync?.clear();sync=null;body.replaceChildren();
        const row=report.rows.find(r=>r.evidence_sha256===select.value);if(!row)return;
        if(!/^[a-f0-9]{64}$/.test(row.evidence_sha256))throw Error('实验身份无效');
        const note=document.createElement('p');
        note.textContent=`未采用实验 · 原几何：${row.original_geometry_passed?'通过':'失败'} · 面积保留失败样本：${row.area_preservation_failure_samples??'未测量'} · 深度：${row.depth_status}。此处不提供验收或默认采用。`;
        const frame=document.createElement('iframe');frame.title='局部修正实验实时对照';
        frame.src=`${base}/experiments/${row.evidence_sha256}/player.html`;
        const status=document.createElement('p');body.append(note,frame,status);
        sync=createCohortSync(status);if(end!==null)sync.seek(time,end);sync.attach(frame,row.candidate_bundle_sha256);
      };
    }catch(error){if(token===revision)container.textContent='实验对照读取失败：'+error.message;}
  }
  return {clear,load,seek(t,d){time=t;end=d;sync?.seek(t,d);}};
}
