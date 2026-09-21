export function appendKneeDetails(container,base,artifact,onSeek){
  const button=document.createElement('button');button.textContent='检查膝盖方向与深度';
  const panel=document.createElement('section');container.append(button,panel);
  button.onclick=async()=>{
    button.disabled=true;panel.textContent='正在比较同帧骨轴…';
    try{
      const response=await fetch(base+'bend-status.json',{cache:'no-store'}),report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(report.artifact_sha256!==artifact)throw Error('候选身份变化');
      panel.replaceChildren();
      const note=document.createElement('p');note.textContent='仅检查源采样时刻的骨轴。深度符号不是人体朝前方向；方向一致也不能证明膝形或裙腿遮挡正确。';panel.append(note);
      const labels={projected_bend_reversed:'可见弯曲方向反转',target_bend_flattened:'目标弯曲投影接近拉直',source_bend_hidden_in_depth:'源弯曲主要藏在深度方向',source_nearly_straight:'源接近伸直',unobservable:'无法观测',projected_side_consistent:'可见弯曲方向一致'};
      for(const side of ['left','right']){
        const rows=report.rows.filter(r=>r.side===side),counts={};for(const r of rows)counts[r.status]=(counts[r.status]||0)+1;
        const text=document.createElement('p');text.textContent=(side==='left'?'左腿':'右腿')+'：'+Object.entries(counts).map(([k,v])=>`${labels[k]} ${v}`).join('；');panel.append(text);
        for(const status of ['projected_bend_reversed','target_bend_flattened','source_bend_hidden_in_depth']){
          const r=rows.find(r=>r.status===status);if(!r)continue;
          const seek=document.createElement('button');seek.textContent=`${labels[status]} · 首次 ${r.time.toFixed(3)} 秒`;seek.onclick=()=>onSeek(r.time);panel.append(seek);
        }
      }
    }catch(error){panel.textContent='无法检查：'+error.message;}finally{button.disabled=false;}
  };
}
