// Supplemental diagnostics do not revise the candidate's historical stage decision.
import {depthCoverageText} from './motion-depth-coverage.js';
export function appendDepthDiagnostics(parent, checks, seek) {
  if (!checks) return;
  const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const details=node('details','');
  details.append(node('summary',`保留的遮挡诊断 · ${checks.failures.length} 条失败记录`),
    node('p','来源深度与当前候选的局部像素重叠检查；不代表整帧渲染验收。阶段接受不清除这些异常，未自动调整前后顺序。'));
  details.append(node('p',depthCoverageText(checks)));
  if (!checks.failures.length) details.append(node('p','该诊断未列出失败记录；完整遮挡检查仍需查看技术状态。'));
  for (const row of checks.failures) {
    const reason={visible_depth_straddle:'同一部件跨越前后关系',
      depth_overlap_pixel_budget:'未测：像素检查预算不足',
      visible_unmapped_order_conflict:'未映射部件存在前后顺序冲突'}[row.reason_code]||row.reason_code;
    const line=node('p',`${row.time.toFixed(3)} 秒 · ${row.pair.join(' / ')} · ${reason} `);
    const button=node('button','查看此时刻');
    button.onclick=()=>seek(row.time);line.append(button);details.append(line);
  }
  parent.append(details);
}
