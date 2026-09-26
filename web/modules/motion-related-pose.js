// Locate exact candidate times; source-frame diagnostics are not visual approval.
export function appendPoseChecks(parent, checks, seek) {
  if (!checks) return;
  const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const details=node('details','');
  details.append(node('summary',`源姿态复测 · ${checks.samples} 个源时刻`),
    node('p',`按本候选 ${checks.yaw_degrees}° 视角与裁剪区间重新计算。只检查骨骼关节，未检查帧间插值、网格轮廓或遮挡；偏差不自动判为可见缺陷。`));
  const locate=(line,time)=>{
    if(!Number.isFinite(time)||time<0)return;
    const button=node('button','定位此姿态');button.onclick=()=>seek(time);line.append(button);
  };
  for(const row of checks.limbs){
    const label=`${row.side==='left'?'左':'右'}${row.limb==='arm'?'臂':'腿'}`;
    const angle=row.max_direction_error_degrees===null?'不可观测':`${row.max_direction_error_degrees.toFixed(2)}°`;
    const line=node('p',`${label} · 最大方向偏差 ${angle} · 最大末端偏差 ${(row.max_endpoint_error_ratio*100).toFixed(2)}% 骨链长度（${row.worst_time.toFixed(3)} 秒） `);
    locate(line,row.worst_time);details.append(line);
  }
  const labels={target_bend_flattened:'膝弯曲投影变平',projected_bend_reversed:'膝弯曲投影方向反转',
    source_bend_hidden_in_depth:'源弯曲主要沿深度方向',unobservable:'弯曲方向不可观测'};
  details.append(node('p',checks.events.length?`${checks.events.length} 处需要检查的膝部采样`:'源采样未发现膝部投影方向异常；这不代表实际外观通过。'));
  for(const row of checks.events){
    const line=node('p',`${row.side==='left'?'左':'右'}膝 · ${labels[row.reason]||'待检查'} · ${row.time.toFixed(3)} 秒（源 ${row.source_time.toFixed(3)} 秒） `);
    locate(line,row.time);details.append(line);
  }
  parent.append(details);
}
