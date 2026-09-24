import {createViewState} from './view-pose-state.js';
import {viewCanvas} from './view-pose-canvas.js';

export function viewEditor(parent,onUse,onInvalidate=()=>{}) {
  const panel=document.createElement('fieldset');panel.hidden=true;parent.append(panel);
  panel.innerHTML=`<legend>新视角画布对应编辑</legend>
    <p>左侧调整新图片上的对应位置；右侧调整同一点的目标姿态。滚轮缩放，拖动空白平移。画布聚焦后可用方向键微调选中点，Shift 加速。每次保存一个姿态时间。</p>
    <div class="view-canvases" style="display:flex;flex-wrap:wrap;gap:12px"><label style="flex:1;min-width:260px">新贴图 UV<canvas aria-label="新视角 UV 画布"></canvas></label><label style="flex:1;min-width:260px">目标姿态<canvas aria-label="新视角姿态画布"></canvas></label></div>
    <button type="button" data-action="fit">适配画布</button>
    <label>控制点 <input aria-label="对应控制点" type="number" min="0" step="1"></label>
    <label>生效起点 <input aria-label="新视角生效起点" type="number" min="0" step="0.01"></label>
    <label>生效终点 <input aria-label="新视角生效终点" type="number" min="0" step="0.01"></label>
    <label>姿态时间 <input aria-label="新视角姿态时间" type="number" min="0" step="0.01"></label>
    <button type="button" data-action="save">保存此时姿态</button>
    <button type="button" data-action="discard">撤销未保存坐标</button>
    <label>已保存姿态 <select aria-label="已保存视角姿态"></select></label>
    <button type="button" data-action="delete">删除选中姿态</button>
    <input aria-label="新视角预览时间轴" type="range" min="0" step="0.001" value="0">
    <button type="button" data-action="play">播放对应预览</button>
    <button type="button" data-action="stop">暂停对应预览</button>
    <button type="button" data-action="use">使用画布结果回交</button>
    <button type="button" data-action="download">下载画布草稿</button>
    <p>此窗口只预览已保存姿态间的线性插值，区间端点暂保持最近姿态；不包含原骨骼动画、附件切换或接触求解。提交候选后须在正式时间轴检查。</p><p role="status"></p>`;
  for(const input of panel.querySelectorAll('input'))input.style.maxWidth='100%';
  const inputs=panel.querySelectorAll('input'),[index,start,end,time,slider]=inputs;
  const select=panel.querySelector('select'),status=panel.querySelector('[role="status"]');
  let state=null,views=[],bitmap=null,backup=null,dirty=false,raf=0,last=0;
  const stop=()=>{cancelAnimationFrame(raf);raf=0;last=0;};
  const say=text=>{status.textContent=text;};
  const draw=()=>{index.value=state.selected;views.forEach(v=>v.draw());};
  const clean=()=>{if(dirty)throw Error('请先保存此时姿态或撤销未保存坐标');};
  function restore(){Object.assign(state.controls,structuredClone(backup.controls));state.points.splice(0,state.points.length,...structuredClone(backup.points));for(const pose of state.value.view_pose.poses)pose.correspondence.target_uv=structuredClone(state.controls.target_uv);dirty=false;draw();}
  function checkpoint(){backup={controls:structuredClone(state.controls),points:structuredClone(state.points)};dirty=false;}
  function list(){select.replaceChildren();for(const pose of state.value.view_pose.poses){const o=document.createElement('option');o.value=pose.time;o.textContent=pose.time+' 秒';select.append(o);}}
  function sample(t){state.sample(t);time.value=t.toFixed(3);slider.value=t;checkpoint();draw();say(`预览 ${t.toFixed(3)} 秒，仅为对应插值`);}
  function handle(fn){return ()=>{try{stop();fn();}catch(e){say(e.message);}};}
  index.onchange=handle(()=>{const i=Number(index.value);if(!Number.isInteger(i)||i<0||i>=state.points.length)throw Error('控制点编号越界');state.select(i);draw();});
  select.onchange=handle(()=>{clean();sample(Number(select.value));});
  slider.oninput=handle(()=>{clean();sample(Number(slider.value));});
  for(const button of panel.querySelectorAll('button'))button.onclick=handle(()=>{
    const action=button.dataset.action;
    if(action==='fit'){views.forEach(v=>v.fit());return;}
    if(action==='discard'){restore();say('已恢复保存前坐标');return;}
    if(action==='stop')return;
    if(action==='save'){state.save(Number(time.value),Number(start.value),Number(end.value));onInvalidate();checkpoint();list();select.value=time.value;slider.value=time.value;say(`已保存 ${state.value.view_pose.poses.length} 个姿态；尚未回交`);return;}
    clean();
    if(action==='delete'){state.remove(Number(select.value));onInvalidate();list();say('已删除选中姿态');return;}
    if(action==='play'){
      if(!state.value.view_pose.poses.length)throw Error('请先保存姿态');
      const tick=now=>{if(!panel.isConnected||panel.hidden){stop();return;}let t=Number(slider.value)+(last?(now-last)/1000:0);last=now;if(t>Number(end.value))t=Number(start.value);sample(t);raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);return;
    }
    const result=state.export();
    if(action==='use'){onUse(result);say('画布结果已加载到回交入口；点击提交后才构建候选');}
    if(action==='download'){const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='view-pose-canvas-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  });
  return {
    load(template,image){
      stop();views.forEach(v=>v.destroy());bitmap?.close();bitmap=image;state=createViewState(template);
      panel.hidden=false;[start.value,end.value]=template.view_pose.interval;time.value=((Number(start.value)+Number(end.value))/2).toFixed(3);slider.max=end.value;
      views=Array.from(panel.querySelectorAll('canvas')).map((c,i)=>viewCanvas(c,state,i?'pose':'uv',changed=>{stop();dirty ||= changed;draw();if(changed){onInvalidate();say('坐标已修改，请保存此时姿态');}}));
      views.forEach(v=>{v.setImage(image);v.fit();});index.max=state.points.length-1;checkpoint();list();draw();say('源网格作为初始参考；请调整对应并保存目标姿态');
    },
    reset(){stop();views.forEach(v=>v.destroy());views=[];bitmap?.close();bitmap=null;state=null;panel.hidden=true;}
  };
}
