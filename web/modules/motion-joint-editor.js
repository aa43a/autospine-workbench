import {createJointWorkflow} from './motion-joint-editor-workflow.js';
import {createJointView} from './motion-joint-editor-view.js';

export function createJointEditor({container,getSelection,inspect,seek=()=>{}}){
  let workflow=null,shown=null;
  const actions={inspect,seek};
  for(const name of ['undo','redo','defaults','save','restore','build','refresh','cancel','retry','change','key','deleteKey','clearKeys','anchor','targets','local','mouthAsset'])
    actions[name]=(...args)=>workflow[name](...args);
  const view=createJointView(container,actions);
  workflow=createJointWorkflow({getSelection,inspect,notify(state,status){
    if(shown!==state.meta){shown=state.meta;if(shown)view.controls(shown,state.config);else view.clear();}
    view.update(state,status);
  }});
  workflow.reset();
  window.addEventListener('pagehide',()=>workflow.close());
  return {load:(job,options)=>workflow.load(job,options),restoreResult:(job,report)=>workflow.restoreResult(job,report),
    reset:()=>workflow.reset(),seek:time=>view.time(time)};
}
