import {windParameters} from './motion-wind-solver.js';
const node=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
export function createWindControls(container,actions){
  let config=null,time=0,busy=false,dragging=false;
  const panel=node('div');panel.className='joint-wind-interaction';
  const preview=node('div');preview.className='joint-wind-preview';
  const previewStatus=node('p','先构建或载入联合候选，即可同帧观察风场效果。');previewStatus.setAttribute('data-wind-preview-status','');
  const previewCanvas=node('canvas');previewCanvas.width=320;previewCanvas.height=360;previewCanvas.hidden=true;
  previewCanvas.setAttribute('data-wind-preview-canvas','');previewCanvas.setAttribute('aria-label','风场同帧角色预览');
  preview.append(node('strong','同帧角色预览'),previewStatus,previewCanvas);
  const dial=node('div');dial.className='joint-wind-dial';dial.tabIndex=0;
  for(const [key,value]of Object.entries({role:'slider','aria-label':'风吹向角度，可拖动或使用左右方向键','aria-valuemin':'0','aria-valuemax':'360'}))dial.setAttribute(key,value);
  const arrow=node('span','➜');arrow.className='joint-wind-arrow';arrow.setAttribute('aria-hidden','true');dial.append(arrow);
  const caption=node('p','0° 向右 · 90° 向上');caption.className='joint-note';
  const actual=node('p');actual.className='joint-note';actual.setAttribute('data-wind','current');
  const enable=node('button','启用风场与可用受风区域');enable.type='button';enable.onclick=()=>actions.enableWind();
  const compareLabel=node('label','无风对照（保留身体惯性）'),compare=node('input');compare.type='checkbox';compare.setAttribute('data-wind','no-wind');
  compare.onchange=()=>actions.noWind(compare.checked);compareLabel.append(compare);
  const description=node('p','风强为 0–100 的视觉强度。先启用区域并构建一次，随后可即时调风与回弹。拖动箭头改变吹向，方向键微调；关闭即时预览可看原结果。');description.className='joint-note';
  const keys=node('div');keys.className='joint-keys';keys.append(node('strong','风强与风向关键帧'));
  const note=node('p','有关键帧时，输入值用于记录当前时间；已有关键帧不会自动改写。风向沿较短方向过渡。循环模式会整周期处理阵风，风场首尾仍需一致。');note.className='joint-note';keys.append(note);
  const buttons=node('div');buttons.className='joint-key-actions';
  for(const [key,label]of [['record','记录当前时间'],['delete','删除当前时间'],['clear','清空风场关键帧']]){
    const button=node('button',label);button.type='button';button.setAttribute('data-wind',key);
    button.onclick=()=>key==='record'?actions.key('wind',time,config.wind):key==='delete'?actions.deleteKey('wind',time):actions.clearKeys('wind');buttons.append(button);
  }
  const list=node('div');list.className='joint-key-list';keys.append(buttons,list);
  panel.append(dial,caption,actual,enable,compareLabel,description,keys,preview);container.append(panel);
  function angle(event){const r=dial.getBoundingClientRect(),x=event.clientX-r.left-r.width/2,y=r.top+r.height/2-event.clientY;
    if(Math.hypot(x,y)<6)return;const degrees=((Math.atan2(y,x)*180/Math.PI)%360+360)%360;actions.change('wind','direction',Math.round(degrees));}
  dial.onpointerdown=event=>{if(busy||event.button!==0)return;dragging=true;dial.setPointerCapture(event.pointerId);angle(event);};
  dial.onpointermove=event=>{if(dragging&&!busy)angle(event);};
  dial.onpointerup=dial.onpointercancel=()=>{dragging=false;};
  dial.onkeydown=event=>{if(busy||!config)return;let next;const step=event.shiftKey?15:1;
    if(['ArrowRight','ArrowUp'].includes(event.key))next=(config.wind.direction+step)%360;
    else if(['ArrowLeft','ArrowDown'].includes(event.key))next=(config.wind.direction-step+360)%360;
    else if(event.key==='Home')next=0;else if(event.key==='End')next=360;else return;
    event.preventDefault();actions.change('wind','direction',next);};
  function frame(){if(!config)return;const [strength,direction]=windParameters(config.wind,time);
    actual.textContent=`当前 ${time.toFixed(3)} 秒：风强 ${config.wind.enabled?strength.toFixed(1):'0（已关闭）'} · 吹向 ${((direction%360+360)%360).toFixed(1)}°${compare.checked?' · 画布正在无风对照':''}`;}
  return {update(value,disabled=false,noWind=false){config=value;busy=disabled;compare.checked=noWind;
    arrow.style.transform=`rotate(${-config.wind.direction}deg)`;
    dial.setAttribute('aria-valuenow',String(config.wind.direction));dial.setAttribute('aria-valuetext',`吹向 ${config.wind.direction} 度`);
    dial.setAttribute('aria-disabled',String(busy));dial.tabIndex=busy?-1:0;
    for(const input of panel.querySelectorAll('button,input'))input.disabled=busy;
    list.replaceChildren();for(const key of config.wind.keys){const button=node('button',`${key.time.toFixed(3)} 秒 · ${key.strength} / ${key.direction}°`);
      button.type='button';button.disabled=busy;button.onclick=()=>actions.seek(key.time);list.append(button);}
    if(!config.wind.keys.length)list.append(node('span','无关键帧，使用固定风强、风向与阵风。'));frame();
  },seek(value){time=value;frame();}};
}
