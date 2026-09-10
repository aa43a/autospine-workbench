import { sleeveProgress } from './sleeve-progress.js';

const routes = { ordinary: '普通绑定', sleeves: '袖装处理', undecided: '稍后决定' };
const endpoints = ['route', 'animated/preparation', 'sleeves/annotation', 'sleeves'];

export async function loadAssetProgress(project, request = fetch) {
  // Lazy reads keep expensive source checks out of the asset catalog hot path.
  const results = await Promise.allSettled(endpoints.map(async endpoint => {
    const response = await request(`/api/projects/${encodeURIComponent(project)}/automation/${endpoint}`, { cache: 'no-store' });
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const value = await response.json();
    if (value.project_id !== project || value.authority !== 'none') throw Error('项目响应不匹配');
    return value;
  }));
  return progressRows(results);
}

export function progressRows(results) {
  const names = ['处理路线', '动画来源', '袖装标注', '袖装任务'];
  return results.map((result, index) => {
    const label = names[index];
    if (result.status !== 'fulfilled') return { label, text: '状态读取失败，请刷新；不能据此判断任务已结束。' };
    const value = result.value;
    if (index === 0) return { label, text: value.stale ? '来源已改变，请重新选择路线。'
      : `${routes[value.choice] || '待选择'}；自动建议不代表人工确认。` };
    if (index === 1) return { label, text: value.source_registered ? '来源已登记；请在工作台检查关节及绑定复核。'
      : value.can_prepare ? '可准备来源，下一步进入绑定规划与复核。' : `来源尚未就绪：${value.reason_code || value.status}` };
    if (index === 2) return { label, text: value.status === 'stale' ? '标注来源已过期，请重新准备并复核。'
      : value.can_build ? '草稿已保存，允许构建候选；不确定区域仍需复核。'
        : value.status === 'ready' ? '画布已准备，尚未保存草稿。' : '尚未创建标注；需要袖装处理时在工作台准备。' };
    const job = value.job;
    if (!job) return { label, text: '当前来源没有可显示的任务；旧来源结果不作为当前完成证据。' };
    if (job.candidate_withdrawn) return { label, text: '候选已撤回；进入袖装修复查看或恢复。' };
    if (['pending', 'running'].includes(job.status)) return { label, text: sleeveProgress(job).label };
    if (job.status === 'failed') return { label, text: `任务失败：${job.reason_code || '原因待检查'}；进入袖装修复重试。` };
    const blocked = (job.result?.records || []).filter(row => row.status === 'blocked');
    const reasons = [...new Set(blocked.map(row => row.reason_code).filter(Boolean))];
    const explanations = { motion_envelope_geometry_failure: '动作范围内变形检查未通过',
      cloth_helper_unobservable: '未找到垂布辅助骨；普通袖需使用独立分支',
      motion_envelope_not_evaluated: '尚无动作检查证据' };
    const detail = reasons.map(reason => explanations[reason] ? `${explanations[reason]}（${reason}）` : reason).join('、');
    if (job.status === 'blocked') return { label, text: `候选被阻塞（${blocked.length} 个区域）：${detail || '请查看 QA'}。` };
    if (job.status === 'needs_review') return { label, text: `候选检查完成，仍待复核${blocked.length ? `；${blocked.length} 个区域被阻塞` : ''}。不代表视觉验收或正式采用。` };
    return { label, text: '进入工作台检查任务结果；不能据此判断已通过验收。' };
  });
}

export function assetProgressPanel(document, project, request) {
  const details = document.createElement('details'), summary = document.createElement('summary');
  summary.textContent = '查看流程状态与下一步'; details.append(summary);
  const output = document.createElement('div'), refresh = document.createElement('button');
  output.setAttribute('aria-live', 'polite'); refresh.type = 'button'; refresh.textContent = '刷新流程状态';
  let busy = false, loaded = false;
  async function load() {
    if (busy) return;
    busy = true; refresh.disabled = true; output.textContent = '正在检查当前来源与任务…';
    try {
      const rows = await loadAssetProgress(project, request);
      output.replaceChildren(...rows.map(row => {
        const p = document.createElement('p'), label = document.createElement('strong');
        label.textContent = `${row.label}：`; p.append(label, document.createTextNode(row.text)); return p;
      }));
      loaded = true;
    } finally { busy = false; refresh.disabled = false; }
  }
  refresh.addEventListener('click', load);
  details.addEventListener('toggle', () => { if (details.open && !loaded) void load(); });
  details.append(output, refresh); return details;
}
