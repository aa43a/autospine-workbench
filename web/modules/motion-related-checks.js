export function contactCheckText(checks) {
  if(!checks)return '脚端轨迹与接触：尚无对应此候选的复测记录。';
  const metric=(name,row)=>`${name}：${row.passed?'通过':'需处理'}，最大误差 ${Number(row.error_px).toFixed(3)} px / 上限 ${Number(row.limit_px).toFixed(3)} px`;
  return `${checks.samples} 个采样 · ${metric('脚端轨迹',checks.moving_ankles)}；${metric(checks.inferred?'推断接触窗口':'接触窗口',checks.ankle_contact)}。仅验证骨骼脚端；鞋底画面接触、前后遮挡及视觉仍待检查。`;
}
