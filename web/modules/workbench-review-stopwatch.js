"use strict";
export function createReviewStopwatch(document,clock=()=>performance.now(),options={}){
 const element=document.createElement('div'),button=document.createElement('button'),status=document.createElement('p');
 button.type='button';button.className='button button-secondary';element.append(button,status);
 let seconds=0,started=null,measured=false,enabled=false;
 function value(){return Math.min(86400,seconds+(started===null?0:Math.max(0,clock()-started)/1000));}
 function render(){button.disabled=!enabled;button.textContent=started===null?'开始 / 继续复核计时':'暂停复核计时';
  status.textContent=measured?`本候选复核计时 ${(value()/60).toFixed(1)} 分钟${started===null?'（已暂停）':'（计时中）'}；随${options.scope==='automatic_binding_audit_session'?'抽查结果':'视觉复核'}保存。`:'尚未计时。开始后可切换到 Runtime 查看；离开复核时请暂停。此计时不代表整个项目人工耗时。';}
 function pause(){seconds=value();started=null;render();}
 button.addEventListener('click',()=>{if(!enabled)return;if(started!==null)pause();else{measured=true;started=clock();render();}options.changed?.();});
 return {element,load(timing){seconds=timing?.seconds||0;measured=Boolean(timing);started=null;render();},
  sync(canEdit){enabled=canEdit;if(!enabled)pause();else render();},
  current(){return measured?{method:'operator_stopwatch_v1',scope:options.scope||'whole_character_visual_review_session',seconds:Math.round(value()*1000)/1000}:null;},
  snapshot(){pause();return this.current();},
  pause};
}
