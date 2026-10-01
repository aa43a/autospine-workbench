import {windParameters} from './motion-wind-solver.js';
const node=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
export function createWindControls(container,actions){
  let config=null,time=0,busy=false,dragging=false;
  const panel=node('div');panel.className='joint-wind-interaction';
  const preview=node('div');preview.className='joint-wind-preview';
  const previewStatus=node('p','先构建或载入联合候选，即可同帧观察风场效果。');previewStatus.setAttribute('data-wind-preview-status','');
  const previewCanvas=node('canvas');previewCanvas.width=320;previewCanvas.height=360;previewCanvas.hidden=true;
  previewCanvas.setAttribute('data-wind-preview-canvas','');previewCanvas.setAttribute('aria-label','有风同帧角色预览');
  const baselineCanvas=node('canvas');baselineCanvas.width=320;baselineCanvas.height=360;baselineCanvas.hidden=true;
  baselineCanvas.setAttribute('data-wind-baseline-canvas','');baselineCanvas.setAttribute('aria-label','无风同帧角色预览');
  const zoomLabel=node('label','观察区域'),zoom=node('select');zoom.setAttribute('aria-label','受风对照观察区域');zoom.setAttribute('data-wind-view','');
  for(const [value,label]of [['whole','全身'],['hair','头发放大'],['cloth','裙袖放大'],['objects','挂饰放大']]){const option=node('option',label);option.value=value;zoom.append(option);}
  zoom.onchange=()=>actions.windView();zoomLabel.append(zoom);
  const canvases=node('div');canvases.className='joint-wind-pair';
  const left=node('div'),right=node('div');left.append(node('strong','无风 · 保留身体惯性'),baselineCanvas);right.append(node('strong','当前风场'),previewCanvas);canvases.append(left,right);
  const delta=node('p');delta.className='joint-note';delta.setAttribute('data-wind-delta','');
  preview.append(node('strong','有风 / 无风 · 同帧同尺寸对照'),previewStatus,zoomLabel,canvases,delta);
  const dial=node('div');dial.className='joint-wind-dial';dial.tabIndex=0;
  for(const [key,value]of Object.entries({role:'slider','aria-label':'风吹向角度，可拖动或使用左右方向键','aria-valuemin':'0','aria-valuemax':'360'}))dial.setAttribute(key,value);
  const arrow=node('span','➜');arrow.className='joint-wind-arrow';arrow.setAttribute('aria-hidden','true');dial.append(arrow);
  const caption=node('p','0° 向右 · 90° 向上');caption.className='joint-note';
  const actual=node('p');actual.className='joint-note';actual.setAttribute('data-wind','current');
  const enable=node('button','启用风场与可用受风区域');enable.type='button';enable.onclick=()=>actions.enableWind();
  const compareLabel=node('label','无风对照（保留身体惯性）'),compare=node('input');compare.type='checkbox';compare.setAttribute('data-wind','no-wind');
  compare.onchange=()=>actions.noWind(compare.checked);compareLabel.append(compare);
  const profileLabel=node('label','受风响应'),profile=node('select');profile.setAttribute('aria-label','受风响应模式');
  for(const [value,label]of [['bounded-equilibrium-v2','自然摆动（推荐）'],['legacy-angular-v1','兼容旧候选']]){const option=node('option',label);option.value=value;profile.append(option);}
  profile.onchange=()=>actions.windProfile(profile.value);profileLabel.append(profile);
  const description=node('p','风强为 0–100 的视觉强度。自然摆动模式保留网格保护，将二维覆盖作为待检查记录。非循环首帧从静止开始，播放或拖到后续时间观察回弹。');description.className='joint-note';
  const keys=node('div');keys.className='joint-keys';keys.append(node('strong','风强与风向关键帧'));
  const note=node('p');note.className='joint-note';keys.append(note);
  const buttons=node('div');buttons.className='joint-key-actions';
  for(const [key,label]of [['record','记录当前时间'],['delete','删除当前时间'],['clear','清空风场关键帧']]){
    const button=node('button',label);button.type='button';button.setAttribute('data-wind',key);
    button.onclick=()=>{const [strength,direction]=windParameters(config.wind,time);
      return key==='record'?actions.key('wind',time,{strength,direction:((direction%360)+360)%360}):key==='delete'?actions.deleteKey('wind',time):actions.clearKeys('wind',time);};buttons.append(button);
  }
  const list=node('div');list.className='joint-key-list';keys.append(buttons,list);
  panel.append(dial,caption,actual,enable,profileLabel,compareLabel,description,keys,preview);container.append(panel);
  function angle(event){const r=dial.getBoundingClientRect(),x=event.clientX-r.left-r.width/2,y=r.top+r.height/2-event.clientY;
    if(Math.hypot(x,y)<6)return;const degrees=((Math.atan2(y,x)*180/Math.PI)%360+360)%360;actions.windParameter('direction',Math.round(degrees),time);}
  dial.onpointerdown=event=>{if(busy||event.button!==0)return;dragging=true;dial.setPointerCapture(event.pointerId);angle(event);};
  dial.onpointermove=event=>{if(dragging&&!busy)angle(event);};
  dial.onpointerup=dial.onpointercancel=()=>{dragging=false;};
  dial.onkeydown=event=>{if(busy||!config)return;let next;const step=event.shiftKey?15:1,direction=windParameters(config.wind,time)[1];
    if(['ArrowRight','ArrowUp'].includes(event.key))next=(direction+step)%360;
    else if(['ArrowLeft','ArrowDown'].includes(event.key))next=(direction-step+360)%360;
    else if(event.key==='Home')next=0;else if(event.key==='End')next=360;else return;
    event.preventDefault();actions.windParameter('direction',next,time);};
  function frame(){if(!config)return;const [strength,direction]=windParameters(config.wind,time);
    const angle=((direction%360+360)%360);
    arrow.style.transform=`rotate(${-angle}deg)`;dial.setAttribute('aria-valuenow',String(angle));dial.setAttribute('aria-valuetext',`吹向 ${angle.toFixed(1)} 度`);
    for(const [key,value]of [['strength',strength],['direction',angle]]){
      const input=container.querySelector(`[data-joint-control="wind.${key}"]`),slider=container.querySelector(`[data-joint-control="wind.${key}-slider"]`);
      if(input&&document.activeElement!==input)input.value=String(Number(value.toFixed(3)));if(slider)slider.value=String(value);
    }
    actual.textContent=`当前 ${time.toFixed(3)} 秒：风强 ${config.wind.enabled?strength.toFixed(1):'0（已关闭）'} · 吹向 ${angle.toFixed(1)}°${compare.checked?' · 主结果正在无风对照':''}`;
    note.textContent=config.wind.keys.length?'时间轴模式：调整滑条会立即更新当前时间的关键帧，可撤销。切换为整段固定风场可点击“清空风场关键帧”；会保留当前风强、风向。':'整段模式：滑条直接作用于整段。记录当前时间后，可制作随时间变化的风场。';
  }
  return {update(value,disabled=false,noWind=false){config=value;busy=disabled;compare.checked=noWind;
    profile.value=config.wind.response_profile??'legacy-angular-v1';
    dial.setAttribute('aria-disabled',String(busy));dial.tabIndex=busy?-1:0;
    for(const input of panel.querySelectorAll('button,input,select'))input.disabled=busy;
    list.replaceChildren();for(const key of config.wind.keys){const button=node('button',`${key.time.toFixed(3)} 秒 · ${key.strength} / ${key.direction}°`);
      button.type='button';button.disabled=busy;button.onclick=()=>actions.seek(key.time);list.append(button);}
    if(!config.wind.keys.length)list.append(node('span','无关键帧，使用固定风强、风向与阵风。'));frame();
  },seek(value){time=value;frame();}};
}
