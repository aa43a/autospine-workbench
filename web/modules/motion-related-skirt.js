export function appendSkirtChecks(parent,checks,seek) {
  if(!checks)return;
  const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const details=node('details','');
  details.append(node('summary',`裙腿遮挡 · ${checks.poses} 个姿态定位`),
    node('p','基于近似裙面模型；没有真实布料深度，也未覆盖整段。结果用于定位，不自动调整绘制顺序。'));
  const labels={no_overlap:'未检测到重叠',uniform_front_proxy:'模型提示腿在前',
    uniform_back_proxy:'模型提示腿在后',requires_partition_or_more_depth:'深度仍不确定',unmeasured:'未完成测量'};
  for(const row of checks.rows){
    const line=node('p',`${row.pair.join(' / ')} · ${Number(row.time).toFixed(3)} 秒 · ${labels[row.status]||'待检查'} `);
    const button=node('button','定位此姿态');button.onclick=()=>seek(row.time);line.append(button);details.append(line);
  }
  parent.append(details);
}
