(async()=>{
  const el=id=>document.getElementById(id);
  const response=await fetch('comparison.json');if(!response.ok)throw Error('对照数据读取失败');
  const data=await response.json();let row,ready=false,playing=false,time=0,duration=0,last=0,generation=0;
  if(data.title)document.querySelector('h1').textContent=data.title;
  if(data.note)document.querySelector('.note').textContent=data.note;
  if(data.headings)['left','right'].forEach((id,i)=>el(id+'-heading').textContent=data.headings[i]);
  const players=()=>['left','right'].map(id=>el(id).contentWindow);
  data.rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.label??r.job;el('character').append(o);});
  function stop(){playing=false;el('play').textContent='播放';}
  function seek(t){if(!ready)return;time=Math.max(0,Math.min(duration,t));for(const w of players())if(!w.characterPlayerControl.seek(time))throw Error('子窗口拒绝同步时间');el('seek').value=time;el('time').textContent=`${time.toFixed(3)} / ${duration.toFixed(3)} 秒`;window.reachComparisonState={ready,time,duration,artifacts:row.views.map(v=>v.artifact)};}
  async function select(initialTime=0){const token=++generation;stop();ready=false;time=0;window.reachComparisonState={ready:false};for(const id of ['play','reset','seek'])el(id).disabled=true;
    row=data.rows[Number(el('character').value)];el('status').textContent='正在加载两个精确候选…';
    ['left','right'].forEach((id,i)=>{el(id).src=row.views[i].url;el(id+'-info').textContent=`Runtime ${row.views[i].runtime_status} · 几何${row.views[i].geometry_passed?'通过':'未通过'} · 不可靠投影样本 ${row.views[i].unreliable_samples}`;});
    const deadline=performance.now()+120000;
    while(token===generation){const ws=players();if(ws.some(w=>w.characterPlayerError))throw Error('子窗口加载失败');
      if(ws.every((w,i)=>w.characterPlayerReady&&w.characterPlayerControl?.artifact===row.views[i].artifact)){
        const states=ws.map(w=>w.characterPlayerState);if(states[0].duration!==states[1].duration)throw Error('对照动作时长不一致');
        duration=states[0].duration;el('seek').max=duration;ready=true;for(const id of ['play','reset','seek'])el(id).disabled=false;
        el('status').textContent='已同步；两侧均为实验，几何、接触和遮挡状态分别保留。';seek(initialTime);return;}
      if(performance.now()>deadline)throw Error('子窗口加载超时');await new Promise(r=>setTimeout(r,100));}
  }
  const fail=e=>{stop();el('status').textContent=e.message;window.reachComparisonError=String(e);};
  el('character').onchange=()=>select().catch(fail);el('seek').oninput=()=>{stop();seek(Number(el('seek').value));};el('reset').onclick=()=>{stop();seek(0);};
  el('play').onclick=()=>{playing=!playing;last=performance.now();el('play').textContent=playing?'暂停':'播放';};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  function tick(now){if(playing&&ready&&duration>0)seek((time+Math.min(.1,(now-last)/1000))%duration);last=now;requestAnimationFrame(tick);}
  const query=new URLSearchParams(location.search),index=Number(query.get('character')??0),start=Number(query.get('time')??0);
  if(!Number.isInteger(index)||index<0||index>=data.rows.length||!Number.isFinite(start)||start<0)throw Error('定位参数无效');
  el('character').value=String(index);await select(start);requestAnimationFrame(tick);
})().catch(e=>{document.getElementById('status').textContent=e.message;window.reachComparisonError=String(e);});
