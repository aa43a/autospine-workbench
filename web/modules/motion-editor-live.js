import {solveCamera} from './motion-camera-solver.js';
import {createEditorRenderer} from './motion-editor-renderer.js';
export function createLiveCharacter(canvas,status){
  let renderer=null,source=null,version=0,frame=null,time=0,keys=[{time:0,yaw:0}],signature=null,result=null;
  let bounds=null;
  function update(){
    frame=null;if(!renderer)return;
    try{
      if(!source){renderer.draw();status.textContent='角色已加载，请选择源动作。';return;}
      const next=source.snapshot_sha256+JSON.stringify(keys);
      let solveMs=window.motionEditorPreviewState?.solve_ms??0;
      if(signature!==next){const start=performance.now();result=solveCamera(renderer.document,source,keys);
        renderer.animation(result.animation);signature=next;solveMs=performance.now()-start;}
      const bones=renderer.draw(time);
      window.motionEditorPreviewState={status:'raw_preview',source_id:source.source_job_id,
        source_snapshot:source.snapshot_sha256,character_artifact:renderer.artifact,time,
        keys:structuredClone(keys),solve_ms:solveMs,bones,unreliable_samples:result.issues.length};
      status.textContent=`实时姿态预览 · ${time.toFixed(3)}秒${result.issues.length?` · ${result.issues.length}处投影可靠性提示`:''}。尚未应用局部修形、接触或遮挡修正。`;
    }catch(e){renderer.clear();signature=null;window.motionEditorPreviewState={status:'unavailable',reason:e.message};status.textContent=e.message;}
  }
  function schedule(){if(frame===null)frame=requestAnimationFrame(update);}
  return {
    clear(){version++;renderer?.dispose();renderer=null;signature=null;window.motionEditorPreviewState=null;},
    async load(base){
      this.clear();const token=version;
      const next=await createEditorRenderer(canvas,base,()=>token===version);
      if(!next)return null;
      if(token!==version){next.dispose();return null;}
      renderer=next;if(bounds)renderer.viewport(bounds);signature=null;schedule();return next.artifact;
    },
    source(value){source=value;signature=null;window.motionEditorPreviewState=null;if(!value)renderer?.clear();else schedule();},
    seek(value,track){time=value;keys=structuredClone(track);schedule();},
    viewport(value){if(JSON.stringify(bounds)===JSON.stringify(value))return;bounds=value;
      if(renderer){renderer.viewport(value??renderer.bounds);schedule();}},
  };
}
