const names={body:'身体主动作',face:'脸部与表情',wind:'全局风场',hair:'发束响应',cloth:'裙袖响应',objects:'挂饰与物件随动'};
const channels={blink:'眨眼',gaze:'视线',brows:'眉毛',mouth:'口型',turn:'五官转向'};
const node=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
export function createJointTimeline(container,{seek,change,focus}){
  const rows=new Map();let duration=0;
  function load(meta){
    clear();duration=meta.duration;container.append(node('h3','联合通道时间轴'));
    const hint=node('p','各轨共用当前时间。已生成区域可实时计算受风响应；拖动时间轴不累积物理状态。新增网格和最终检查在构建时完成。');hint.className='joint-note';container.append(hint);
    for(const [group,label]of Object.entries(names)){
      if(group==='wind'&&!meta.defaults?.wind)continue;
      const row=node('div');row.className='joint-track';
      const enabled=node('input');enabled.type='checkbox';enabled.setAttribute('aria-label',`时间轨：${label}开关`);
      enabled.onchange=()=>change(group,'enabled',enabled.checked);if(group==='body'){enabled.checked=true;enabled.disabled=true;}
      const title=node('button',label);title.type='button';title.onclick=()=>group==='body'?seek(0):focus(group);
      const rail=node('div');rail.className='joint-track-rail';
      const input=node('input');input.type='range';input.min=0;input.max=duration;input.step='any';input.value=0;input.setAttribute('aria-label',`${label}时间`);
      input.oninput=()=>seek(Number(input.value));const ticks=node('div');ticks.className='joint-track-samples';rail.append(input,ticks);
      const note=node('span');note.className='joint-track-note';row.append(enabled,title,rail,note);container.append(row);rows.set(group,{enabled,input,note,ticks});
    }
  }
  function update(config,busy=false){
    for(const [group,row]of rows){
      row.input.disabled=busy;
      if(group==='body'){row.note.textContent='保留原动作';continue;}
      row.enabled.checked=Boolean(config[group]?.enabled);row.enabled.disabled=busy;
      row.ticks.replaceChildren();
      if(group==='face'){
        let count=0;
        for(const [channel,label]of Object.entries(channels))for(const key of config.face[channel]?.keys??[]){
          count++;const tick=node('span');tick.style.left=`${Math.max(0,Math.min(100,key.time/duration*100))}%`;tick.title=`${label} ${key.time.toFixed(3)} 秒`;row.ticks.append(tick);
        }
        row.note.textContent=!row.enabled.checked?'未启用':count?`${count} 个关键帧`:'自动眨眼 / 固定参数';
      }else if(group==='wind'){
        for(const key of config.wind.keys){const tick=node('span');tick.style.left=`${key.time/duration*100}%`;tick.title=`风强 ${key.strength} · 吹向 ${key.direction}° · ${key.time.toFixed(3)} 秒`;row.ticks.append(tick);}
        row.note.textContent=!row.enabled.checked?'未启用':config.wind.keys.length?`${config.wind.keys.length} 个风场关键帧`:'固定风 + 阵风';
      }else row.note.textContent=!row.enabled.checked?'未启用':config[group].slots?.length?`${config[group].slots.length} 个选定区域`:'全部可用区域';
    }
  }
  function clear(){container.replaceChildren();rows.clear();duration=0;}
  return {load,update,clear,seek(time){for(const row of rows.values())row.input.value=Math.max(0,Math.min(duration,time));}};
}
