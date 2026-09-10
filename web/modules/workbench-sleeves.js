import { automationEndpoint, projectIdentity } from './workbench-automation-contract.js';
import { sleeveProgress } from './sleeve-progress.js';

const ACTIVE = new Set(['pending', 'running']);
const REASONS = { sleeve_draft_missing: '尚未保存袖装区域标注。', sleeve_draft_changed: '袖装标注已变化，请重新构建。',
  project_snapshot_stale: '项目已变化，请保存校正后重新构建。', sleeve_job_interrupted: '上次任务已中断，重新构建将校验并复用完成的步骤。',
  sleeve_cached_output_changed: '缓存文件已变化，已阻止下载。', sleeve_workflow_failed: '构建失败，可重新构建以续跑。',
  sleeve_candidate_withdrawn: '候选已撤回，请恢复后再下载。',
  sleeve_visibility_conflict: '候选展示状态已在其他窗口变化，请刷新后再操作。',
  pipeline_preview_not_ready: '当前候选尚不可用，请查看检查结果或重新构建。' };

const REGION_REASONS = {
  motion_envelope_geometry_failure: '受限动作中存在网格几何失败，已阻塞下载。请复核袖口与手、垂布的归属和连接处变形；修正后重新构建。',
  target_interpolation_geometry_failure: 'Spine 动画关键帧之间的插值未通过几何检查，已阻塞下载。需修正过渡变形并重新构建。',
  official_core_numeric_failure: '官方核心数值验证未通过，已阻塞下载。需检查导出动画与源网格的差异，修复后重新构建。',
  official_framebuffer_contact_failure: '官方帧缓冲检测到袖口接触采样空白，已阻塞下载。请复核接触处裂缝并修正后重新构建。',
  runtime_and_alpha_contact_required: '候选尚缺官方 Runtime 与袖口接触证据。请配置受支持的官方验证环境后重新构建。',
  official_core_required: '官方核心数值验证尚未通过。请检查官方验证环境并重新构建；帧缓冲结果不能替代核心验证。',
  official_framebuffer_required: '官方核心数值已通过，尚缺帧缓冲接触证据。请检查官方捕获环境并重新构建。',
  sleeve_occlusion_review_required: '请复核手与垂布的接触、重叠是否合理；已选袖口采样通过仍不代表完整视觉验收通过。',
};

export function sleeveReasonMessage(reason) {
  return REGION_REASONS[reason] || REASONS[reason]
    || (reason ? `尚未识别此检查原因（${reason}）。请保留原因并反馈排查，不能据此判断通过。`
      : '结果未提供具体原因，请刷新状态；仍缺失时反馈排查。');
}

export function contactMessage(value) {
  if (!value) return '软件接缝尚未检查；GPU 未验证。';
  return `软件接缝：采样 ${value.tested_samples}，空白失败 ${value.failed_samples}，源图不可观测界面 ${value.unobservable_interfaces}；GPU 未验证。`;
}

export function overlapMessage(value) {
  if (!value) return '软件重叠尚未检查；GPU 未验证。';
  return `软件重叠：检查 ${value.frames} 帧，新增双覆盖 ${value.affected_frames} 帧，单对峰值 ${value.peak_excess_pair_pixels} 像素；仅诊断，GPU 未验证。`;
}

export function framebufferMessage(value) {
  if (!value) return '官方帧缓冲尚未捕获。';
  const overlap = value.overlap_peak_pairs ? `重叠峰值 ${value.overlap_affected_peaks}/${value.overlap_peak_pairs} 组出现新增双覆盖，峰值 ${value.overlap_peak_pixels} 像素`
    : '软件诊断未给出重叠峰值，尚未完成全域遮挡验收';
  return `官方 WebGL（SwiftShader）：${value.frames} 帧，袖口空白失败 ${value.failed_samples}；${overlap}。遮挡仍需复核。`;
}

export function readSleeveJob(value, project) {
  if (value?.schema !== 'autospine.sleeve-web-job/v1' || value.project_id !== project || value.authority !== 'none'
    || !/^job-[a-f0-9]{32}$/.test(value.job_id) || !['pending', 'running', 'needs_review', 'blocked', 'failed'].includes(value.status)) throw Error('袖装任务响应无效。');
  if ((value.candidate_withdrawn !== undefined && typeof value.candidate_withdrawn !== 'boolean')
    || (value.visibility_revision !== undefined && (!Number.isSafeInteger(value.visibility_revision) || value.visibility_revision < 0))) throw Error('袖装展示状态无效。');
  if (value.result && (value.result.project_id !== project || value.result.authority !== 'none'
    || value.result.production_authorized !== false || !Array.isArray(value.result.records))) throw Error('袖装结果响应无效。');
  return value;
}

export function createWorkbenchSleeves(document, hooks, options = {}) {
  let identity = null, generation = 0, timer = null, overview = null, job = null, busy = false, error = '', editable = false, polls = 0;
  const schedule = options.schedule || setTimeout, unschedule = options.unschedule || clearTimeout;
  const view = options.view || createView(document, { start, refresh, withdraw: () => visibility('withdraw'), restore: () => visibility('restore') });
  const context = () => hooks.context();
  const current = token => token === generation && identity === projectIdentity(context());
  const endpoint = () => `${automationEndpoint(context().projectId)}/sleeves`;
  const stop = () => { if (timer !== null) unschedule(timer); timer = null; };
  function render() {
    const safe = editable && !context().dirty && !context().saving && !context().loading;
    const reviews = [];
    if (safe && !error && !job?.candidate_withdrawn && job?.result) {
      const completed = new Set((job.result.steps || []).filter(s => s.status === 'succeeded').map(s => s.id));
      const stage = ['repair', 'cuff', 'boundary'].find(s => completed.has(s));
      const base = `${endpoint()}/jobs/${job.job_id}/view`;
      if (stage) reviews.push({ label: '打开修正时间轴', url: `${base}/${stage}/${encodeURIComponent(context().projectId)}/index.html` });
      if (completed.has('framebuffer')) reviews.push({ label: '查看官方捕获与重叠', url: `${base}/framebuffer/index.html` });
    }
    view.render({ canStart: Boolean(identity && safe && overview?.can_build && !busy && !ACTIVE.has(job?.status)),
      reviews, progress: sleeveProgress(job),
      canRefresh: Boolean(identity && !busy), active: busy || ACTIVE.has(job?.status),
      withdrawn: Boolean(job?.candidate_withdrawn),
      canVisibility: Boolean(identity && safe && !busy && job?.status === 'needs_review'
        && (job.candidate_withdrawn || job.result?.records.some(r => r.status === 'candidate_exported' && r.download))),
      message: error || (!safe ? '请先保存校正并等待当前操作完成。' : job?.reason_code ? sleeveReasonMessage(job.reason_code)
        : job?.candidate_withdrawn ? '当前候选已撤回。恢复会重新校验来源与候选文件；标注和正式项目保持不变。'
        : ACTIVE.has(job?.status) ? `${sleeveProgress(job).label}。自动刷新中；修正阶段可能包含多轮求解，可切换页面等待。`
          : job?.status === 'blocked' ? '所有区域均被质量检查阻塞，请查看逐袖原因。'
          : job?.status === 'needs_review' ? '构建完成，请逐袖检查结果。' : overview?.can_build ? '可从已保存的区域标注重建袖装候选。' : '当前项目尚无已保存的袖装区域标注。'),
      rows: (safe && !error && !job?.candidate_withdrawn ? job?.result?.records || [] : []).map((r, index) => ({ ...r,
        url: r.status === 'candidate_exported' && r.download ? `${endpoint()}/jobs/${job.job_id}/download/${index}` : null })) });
  }
  function queue(token) {
    stop();
    if (!current(token) || !ACTIVE.has(job?.status)) return;
    if (++polls > 3600) { error = '状态查询已暂停；点击刷新继续查看，后台任务仍在执行。'; render(); return; }
    timer = schedule(() => { timer = null; void request(false, true); }, 2000);
  }
  async function request(create = false, poll = false, action = null) {
    if (!identity || busy) return;
    const token = generation, saved = { ...context() }, base = endpoint(), jobId = job?.job_id; busy = true; error = ''; render();
    try {
      const url = action ? `${base}/jobs/${jobId}/${action}` : poll ? `${base}/jobs/${jobId}` : base;
      const body = { expected_resolved_sha256: saved.resolvedSha };
      if (action) body.expected_visibility_revision = job.visibility_revision ?? 0;
      const value = await hooks.apiRequest(url, create || action ? { method: 'POST', headers: { 'X-Autospine-Intent': 'pipeline-preview' },
        body: JSON.stringify(body) } : { cache: 'no-store' });
      if (!current(token)) return;
      if (create || poll || action) {
        const next = readSleeveJob(value, saved.projectId);
        if ((poll || action) && next.job_id !== jobId) throw Error('袖装任务不匹配。');
        job = next;
      }
      else {
        if (value.project_id !== saved.projectId || value.authority !== 'none' || typeof value.can_build !== 'boolean') throw Error('袖装能力响应无效。');
        overview = value; job = value.job ? readSleeveJob(value.job, saved.projectId) : null;
      }
    } catch (exc) { if (current(token)) error = REASONS[exc.payload?.reason_code] || '袖装请求失败，请刷新重试。'; }
    finally { if (current(token)) { busy = false; render(); if (!error) queue(token); } }
  }
  function start() {
    if (!editable || context().dirty || context().saving || context().loading || !overview?.can_build || ACTIVE.has(job?.status)) return;
    polls = 0; stop(); return request(true);
  }
  function refresh() { polls = 0; stop(); return request(); }
  function visibility(action) {
    if (!editable || context().dirty || context().saving || context().loading || busy || job?.status !== 'needs_review') return;
    if (action === 'withdraw' && (job.candidate_withdrawn || !job.result?.records.some(r => r.status === 'candidate_exported' && r.download))) return;
    if (action === 'restore' && !job.candidate_withdrawn) return;
    stop(); return request(false, false, action);
  }
  function sync(model) {
    editable = model.preparationEditable;
    const next = projectIdentity(context());
    if (next !== identity) {
      generation++; stop(); identity = next; overview = job = null; busy = false; error = ''; polls = 0;
      if (identity) void request();
    }
    render();
  }
  return { element: view.element, sync, start, refresh, withdraw: () => visibility('withdraw'), restore: () => visibility('restore'),
    dispose() { generation++; stop(); identity = null; } };
}

function createView(document, callbacks) {
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const element = node('section'), title = node('h3', '袖装候选'), build = node('button', '重建袖装候选'), refresh = node('button', '刷新状态');
  element.className = 'sleeve-dashboard';
  title.textContent = '袖装修复与验证';
  const headline = node('h2'), progress = node('progress'), stages = node('ol'), tally = node('p');
  stages.className = 'sleeve-stages'; progress.setAttribute('aria-label','已完成的构建阶段');
  const status = node('p'), reviews = node('nav'), rows = node('ul'); status.setAttribute('role', 'status');
  const withdraw = node('button', '撤回当前候选'), restore = node('button', '恢复当前候选');
  withdraw.type = restore.type = 'button'; withdraw.addEventListener('click', callbacks.withdraw); restore.addEventListener('click', callbacks.restore);
  build.type = refresh.type = 'button'; build.addEventListener('click', callbacks.start); refresh.addEventListener('click', callbacks.refresh);
  element.append(title, headline, progress, tally, build, refresh, withdraw, restore, status, reviews, stages, rows,
    node('p', '支持动作范围：前臂 ±30° / 手 ±30° / 垂布 ±10°，包含单轴及组合测试；不代表任意三轴组合均已验证。'),
    node('p', 'Spine 4.3.26 候选；官方核心数值验证不包含 GPU 渲染与透明接缝检查，也不代表正式采用。'));
  return { element, render(model) {
    const p = model.progress;
    headline.textContent = p.label; progress.max = p.total; progress.value = p.count;
    tally.textContent = `已完成 ${p.count} / ${p.total} 个阶段 · 阶段数不代表耗时比例`;
    stages.replaceChildren(...p.stages.map(s => { const li = node('li', `${s.state === 'done' ? '✓' : s.state === 'current' ? '●' : '○'} ${s.name}`); li.setAttribute('data-state', s.state); return li; }));
    build.textContent = model.active ? '构建进行中…' : model.rows.length ? '重新构建袖装' : '一键构建袖装';
    build.disabled = !model.canStart; refresh.disabled = !model.canRefresh; status.textContent = model.message;
    withdraw.hidden = model.withdrawn || !model.canVisibility; restore.hidden = !model.withdrawn;
    withdraw.disabled = restore.disabled = !model.canVisibility;
    element.setAttribute('aria-busy', String(model.active));
    reviews.replaceChildren(...model.reviews.map(r => { const a = node('a', r.label); a.href = r.url; a.target = '_blank'; a.rel = 'noopener'; a.setAttribute('style', 'margin-right:1em'); return a; }));
    rows.replaceChildren(...model.rows.map(r => {
      const row = node('li', `${r.layer_id} · ${r.status === 'candidate_exported' ? '候选已导出' : '候选已阻塞'} · ${r.runtime_status === 'passed' || r.runtime_status === 'core_passed' ? '核心数值验证通过' : '核心验证未通过或未执行'}`);
      row.append(node('p', sleeveReasonMessage(r.reason_code)));
      if (r.official_framebuffer) row.append(node('p', framebufferMessage(r.official_framebuffer)));
      else row.append(node('p', contactMessage(r.software_contact)), node('p', overlapMessage(r.software_overlap)),
        node('p', framebufferMessage(null)));
      if (r.url) { const a = node('a', ' 下载候选 ZIP'); a.href = r.url; row.append(a); }
      return row;
    }));
  } };
}
