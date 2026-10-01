import {createJointWorkflow} from './motion-joint-editor-workflow.js';
import {createJointView} from './motion-joint-editor-view.js';

export function createJointEditor({container,getSelection,inspect,seek=()=>{},preview=()=>null}){
  let workflow=null,shown=null,previewEnabled=true,noWind=false,lastStatus={},time=0;
  const actions={inspect,seek};
  actions.preview=enabled=>{previewEnabled=enabled;if(!enabled)noWind=false;paint(workflow.state,lastStatus);};
  actions.noWind=enabled=>{noWind=enabled;previewEnabled=true;paint(workflow.state,lastStatus);};
  for(const name of ['undo','redo','defaults','save','restore','build','refresh','cancel','retry','change','key','deleteKey','clearKeys','anchor','targets','local','mouthAsset','enableWind','windParameter','windProfile','clothProfile'])
    actions[name]=(...args)=>workflow[name](...args);
  actions.windParameter=(key,value,current=time)=>{
    if(workflow.state.config?.wind?.keys.length)seek(current);
    workflow.windParameter(key,value,current);
  };
  actions.windView=()=>window.dispatchEvent(new Event('autospine:wind-view'));
  const view=createJointView(container,actions);
  function paint(state,status){
    lastStatus=status;
    if(shown!==state.meta){shown=state.meta;if(shown)view.controls(shown,state.config);else view.clear();}
    const current=preview(state.meta?{enabled:previewEnabled,parent_job_id:state.meta.parent_job_id,
      artifact_sha256:state.meta.artifact_sha256,config:state.config,noWind}:null);
    view.update(state,{...status,previewEnabled,noWind,preview:current});
  }
  workflow=createJointWorkflow({getSelection,inspect,notify:paint});
  workflow.reset();
  window.addEventListener('pagehide',()=>workflow.close());
  return {load:(job,options)=>{noWind=false;return workflow.load(job,options);},restoreResult:(job,report)=>workflow.restoreResult(job,report),
    reset:()=>{noWind=false;return workflow.reset();},seek:value=>{time=value;view.time(value);}};
}
