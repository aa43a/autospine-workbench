// Read-only navigation over recorded samples, never interpolation or acceptance.
import {depthReason,depthTimeLabel} from './motion-depth-reason.js';

export function appendDepthTimeline(panel,job,readiness,onSeek,onRegions){
  const button=document.createElement('button');button.textContent='展开完整遮挡定位（含未测记录）';
  const body=document.createElement('section');body.setAttribute('aria-live','polite');
  button.onclick=async()=>{
    button.disabled=true;body.textContent='正在读取原始遮挡记录…';
    try{
      const base=`/api/motions/${job.job_id}/view/`;
      const response=await fetch(base+'depth-navigation.json',{cache:'no-store'});
      const report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(!readiness.skeleton_sha256||report.skeleton_sha256!==readiness.skeleton_sha256||
        report.artifact_sha256!==job.result.artifact_sha256)
        throw Error('候选骨架证据已变化，请重新检查');
      if(report.profile!=='external-motion-depth-navigation-v1'||!Array.isArray(report.groups)||
        report.authority!=='none'||report.order_changed!==false)throw Error('此报告未提供有效定位记录');
      const groups=report.groups;
      body.replaceChildren();
      const note=document.createElement('p');
      note.textContent=`原排序记录 ${report.original_order_records} 条；合并未测项目后 ${report.diagnostic_records} 条诊断，${groups.length} 组关系，${report.navigable_samples} 个定位采样。诊断数不是画面错误数；原检查可能提前停止，这些不是全部潜在问题，首末时间之间也不代表连续失败或完整验证。`;
      body.append(note);
      for(const group of groups){
        const section=document.createElement('details'),title=document.createElement('summary');
        if(!Array.isArray(group.samples)||!group.samples.length||group.samples.some(s=>
          !Number.isFinite(s.time)||s.time<0||!Array.isArray(s.order_times)))throw Error('定位时间无效');
        const first=group.samples[0].time,last=group.samples.at(-1).time;
        const [name,explanation]=depthReason(group.reason);
        title.textContent=`${group.pair.join(' ↔ ')||'未指定部件'} · ${name} · ${group.samples.length} 个采样 · ${first.toFixed(3)}–${last.toFixed(3)} 秒`;
        const help=document.createElement('p');help.textContent=`${explanation} 时间来源：${depthTimeLabel(group.time_source)}。原代码：${group.reason}`;
        const slider=document.createElement('input');slider.type='range';slider.min='0';
        slider.max=String(group.samples.length-1);slider.step='1';slider.value='0';
        slider.setAttribute('aria-label','遮挡诊断采样序号');
        const label=document.createElement('span'),link=document.createElement('a');
        link.textContent='定位此采样';
        const update=()=>{
          const index=Number(slider.value),sample=group.samples[index],time=sample.time;
          const anchors=sample.order_times.filter(t=>t!==time);
          label.textContent=` ${index+1}/${group.samples.length} · ${time.toFixed(6)} 秒 `+
            (anchors.length?`（原判定起点 ${anchors.map(t=>t.toFixed(6)).join('、')} 秒） `:'');
          link.href=base+`player.html?time=${encodeURIComponent(time)}`;
          if(onSeek)link.onclick=event=>{event.preventDefault();onSeek(time);};
          else{link.target='_blank';link.rel='noopener';}
        };
        slider.oninput=update;update();section.append(title,help,slider,label,link);
        if(onRegions&&group.pair.length){
          const isolate=document.createElement('button');isolate.textContent='同页隔离相关部件';
          isolate.onclick=()=>{onSeek?.(group.samples[Number(slider.value)].time);onRegions(group.pair);};section.append(isolate);
        }
        body.append(section);
      }
    }catch(error){body.textContent='无法读取完整定位：'+error.message;}
    finally{button.disabled=false;}
  };
  panel.append(button,body);
}
