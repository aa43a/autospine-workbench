import {appendDepthDetails} from './motion-depth-details.js';
export function appendDepthSummary(item, job, inspection) {
  const status = job.result.depth_order_status;
  const labels = {depth_order_sampled_candidate: '已生成受重叠约束的动态顺序，仍需阶段验收',
    depth_overlap_no_change: '同帧采样未要求改序；保留原顺序',
    depth_candidates_need_review: '发现换序或跨平面候选，保留原顺序',
    depth_evidence_no_switch: '已检查源深度，未发现换序建议；像素遮挡尚未验收',
    depth_mapping_unavailable: '缺少可用的手臂与躯干配对'};
  if (!labels[status]&&!job.result.repair_profile&&!job.result.local_depth_evidence_sha256) return;
  const line = document.createElement('p'); line.textContent = `遮挡：${labels[status]||'前后关系尚未验收，可查看当前候选诊断'}`;
  const link = document.createElement('a'); link.textContent = '查看遮挡时间点';
  link.href = `/api/motions/${job.job_id}/view/depth.html`; link.target = '_blank'; link.rel = 'noopener';
  item.append(line);
  if(labels[status]||job.result.repair_depth_overlap)item.append(link);
  appendDepthDetails(item,job,inspection);
}
