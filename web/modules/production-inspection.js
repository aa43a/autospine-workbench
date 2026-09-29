// The diagnostic iframe is separate so ordinary progress polling cannot reset it.
export function inspectionControls(panel,job){
  const label=document.createElement('p'),frame=document.createElement('iframe');
  frame.title='异常定位播放器';frame.hidden=true;panel.append(label,frame);
  let time=0,regions=[];
  function control(){try{const c=frame.contentWindow?.characterPlayerControl;return c?.artifact===job.result.artifact_sha256?c:null;}catch{return null;}}
  function show(){frame.hidden=false;label.textContent='异常定位：显示当前候选，不代表该异常已经修复。';frame.scrollIntoView({block:'center'});}
  function load(){const url=new URL(`/api/motions/${job.job_id}/view/player.html`,location.origin);url.searchParams.set('time',String(time));for(const r of regions)url.searchParams.append('region',r);if(regions.length)url.searchParams.set('mode','isolate');frame.src=url.href;show();}
  return {
    onSeek(value){if(!Number.isFinite(value)||value<0)return;time=value;const c=control();if(c?.seek(value)){show();return;}load();},
    onRegions(value){regions=value.slice(0,2);if(control()?.inspectRegions(regions)){show();return;}load();},
    onInspect(slot,index,animation){return control()?.inspectTriangle(slot,index,animation)??false;},
  };
}
