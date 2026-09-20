export function appendDepthSummary(item, job) {
  const status = job.result.depth_order_status;
  const labels = {depth_candidates_need_review: '发现换序或跨平面候选，保留原顺序',
    depth_evidence_no_switch: '已检查源深度，未发现换序建议；像素遮挡尚未验收',
    depth_mapping_unavailable: '缺少可用的手臂与躯干配对'};
  if (!labels[status]) return;
  const line = document.createElement('p'); line.textContent = `遮挡：${labels[status]}`;
  const link = document.createElement('a'); link.textContent = '查看遮挡时间点';
  link.href = `/api/motions/${job.job_id}/view/depth.html`; link.target = '_blank'; link.rel = 'noopener';
  item.append(line, link);
}
