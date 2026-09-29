import {createJointWorkflow} from './motion-joint-editor-workflow.js';
import {createJointView} from './motion-joint-editor-view.js';

export function createJointEditor({container,getSelection,inspect,seek=()=>{},preview=()=>null}){
  let workflow=null,shown=null,previewEnabled=true,lastStatus={};
  const actions={inspect,seek};
  actions.preview=enabled=>{previewEnabled=enabled;paint(workflow.state,lastStatus);};
  for(const name of ['undo','redo','defaults','save','restore','build','refresh','cancel','retry','change','key','deleteKey','clearKeys','anchor','targets','local','mouthAsset'])
    actions[name]=(...args)=>workflow[name](...args);
  const view=createJointView(container,actions);
  function paint(state,status){
    lastStatus=status;
    if(shown!==state.meta){shown=state.meta;if(shown)view.controls(shown,state.config);else view.clear();}
    const current=preview(state.meta?{enabled:previewEnabled,parent_job_id:state.meta.parent_job_id,
      artifact_sha256:state.meta.artifact_sha256,config:state.config}:null);
    view.update(state,{...status,previewEnabled,preview:current});
  }
  workflow=createJointWorkflow({getSelection,inspect,notify:paint});
  workflow.reset();
  window.addEventListener('pagehide',()=>workflow.close());
  return {load:(job,options)=>workflow.load(job,options),restoreResult:(job,report)=>workflow.restoreResult(job,report),
    reset:()=>workflow.reset(),seek:time=>view.time(time)};
}
