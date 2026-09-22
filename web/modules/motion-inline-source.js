import {createSourcePlayer} from './motion-source-player.js';

export function createInlineSource(parent, job, target, onTime) {
  const node=(tag,text)=>{const el=document.createElement(tag);if(text)el.textContent=text;return el;};
  const button=node('button','同步源骨架对照');
  const panel=node('section');panel.hidden=true;
  const note=node('p');note.setAttribute('aria-live','polite');
  const rangeInfo=node('p');
  const canvas=node('canvas');canvas.width=640;canvas.height=380;
  const slider=node('input');slider.type='range';slider.step='0.001';slider.min=0;
  slider.setAttribute('aria-label','源与角色共用时间轴');
  const play=node('button','播放');const label=node('output');
  const view=node('select');view.setAttribute('aria-label','源骨架观察视角');
  view.add(new Option('源投影视角',''));view.add(new Option('正面','front'));view.add(new Option('侧面','side'));
  slider.style.width='55%';
  panel.append(note,rangeInfo,view,canvas,play,slider,label);parent.append(button,panel);
  let report=null, revision=0, suppress=false, lastTime=0;
  const disabledControls=new Map();
  function release(){for(const [el,disabled] of disabledControls)el.disabled=disabled;disabledControls.clear();}
  const player=createSourcePlayer(canvas,slider,play,label,time=>{
    if(report&&!suppress)onTime(time-report.source_start);
  });
  player.clear(); view.onchange=()=>player.setView(view.value||null);
  button.onclick=async()=>{
    const token=++revision;panel.hidden=false;button.disabled=true;note.textContent='正在核对来源与片段时间…';
    try {
      const response=await fetch(`/api/motions/${job.job_id}/view/source-comparison.json`,{cache:'no-store'});
      const value=await response.json();if(token!==revision)return;
      if(!response.ok)throw Error(value.reason_code||'读取失败');
      const win=target();
      if(value.artifact_sha256!==job.result.artifact_sha256||win?.characterPlayerControl?.artifact!==value.artifact_sha256)
        throw Error('请等待匹配候选播放器加载');
      if(Math.abs(win.characterPlayerState.duration-value.duration)>.002)throw Error('源片段与角色时长不同');
      report=value;suppress=true;
      rangeInfo.textContent=`源动作 ${value.source_start.toFixed(3)}–${value.source_end.toFixed(3)} 秒，对应角色 0–${value.duration.toFixed(3)} 秒；下方显示源时间。`;
      player.load(value.preview,{start:value.source_start,end:value.source_end});
      player.seek(value.source_start+lastTime);suppress=false;
      for(const id of ['motion','play','reset','time']) {
        const el=win.document.getElementById(id);
        if(el){if(!disabledControls.has(el))disabledControls.set(el,el.disabled);el.disabled=true;}
      }
      note.textContent='共用时间轴；骨架显示最近源采样，观察视角不修改角色动画。';
      onTime(lastTime);
    } catch(error){report=null;player.clear();release();note.textContent='无法同步：'+error.message;}
    finally {suppress=false;if(token===revision)button.disabled=false;}
  };
  return {
    seek(time){lastTime=time;if(report)player.seek(report.source_start+time);},
    clear(){revision++;report=null;player.clear();release();panel.hidden=true;button.disabled=false;lastTime=0;},
  };
}
