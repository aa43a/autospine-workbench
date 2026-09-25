// One request and one editor tree per immutable candidate panel.
export function diagnosticPanel(parent, {label, load, render}) {
  const make=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const button=make('button',label), panel=make('section','');
  panel.hidden=true;
  const status=make('p','');status.setAttribute('role','status');
  panel.append(status);
  let state='idle', pending=null;
  const update=()=>{
    button.textContent=state==='failed'?'重试定位变形区域':panel.hidden ? (state==='ready'?'展开变形区域与处理方案':label)
      : (state==='loading'?'收起定位进度':'收起变形区域与处理方案');
    button.setAttribute('aria-expanded',String(!panel.hidden));
  };
  button.onclick=()=>{
    if(state==='ready'||state==='loading') {
      panel.hidden=!panel.hidden;update();return pending;
    }
    state='loading';panel.hidden=false;panel.replaceChildren(status);
    panel.setAttribute('aria-busy','true');update();
    const started=Date.now();
    const tick=()=>{status.textContent=`正在定位当前候选的采样异常，已等待 ${Math.floor((Date.now()-started)/1000)} 秒。首次计算可能较慢，可收起后继续播放；再次展开不会重复计算。`;};
    tick();const timer=setInterval(tick,1000);
    pending=(async()=>{
      try {
        const report=await load();
        panel.replaceChildren();render(panel,report);state='ready';
      } catch(error) {
        state='failed';panel.replaceChildren(status);
        status.textContent='无法定位：'+error.message+'。可点击入口重试。';
      } finally {
        clearInterval(timer);panel.setAttribute('aria-busy','false');
        update();pending=null;
      }
    })();
    return pending;
  };
  update();parent.append(button,panel);
}
