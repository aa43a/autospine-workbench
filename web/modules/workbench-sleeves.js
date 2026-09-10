import { automationEndpoint, projectIdentity } from './workbench-automation-contract.js';

const ACTIVE = new Set(['pending', 'running']);
const REASONS = { sleeve_draft_missing: '尚未保存袖装区域标注。', sleeve_draft_changed: '袖装标注已变化，请重新构建。',
  project_snapshot_stale: '项目已变化，请保存校正后重新构建。', sleeve_job_interrupted: '上次任务已中断，重新构建将校验并复用完成的步骤。',
  sleeve_cached_output_changed: '缓存文件已变化，已阻止下载。', sleeve_workflow_failed: '构建失败，可重新构建以续跑。' };

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
  if (value.result && (value.result.project_id !== project || value.result.authority !== 'none'
    || value.result.production_authorized !== false || !Array.isArray(value.result.records))) throw Error('袖装结果响应无效。');
  return value;
}

export function createWorkbenchSleeves(document, hooks, options = {}) {
  let identity = null, generation = 0, timer = null, overview = null, job = null, busy = false, error = '', editable = false, polls = 0;
  const schedule = options.schedule || setTimeout, unschedule = options.unschedule || clearTimeout;
  const view = options.view || createView(document, { start, refresh });
  const context = () => hooks.context();
  const current = token => token === generation && identity === projectIdentity(context());
  const endpoint = () => `${automationEndpoint(context().projectId)}/sleeves`;
  const stop = () => { if (timer !== null) unschedule(timer); timer = null; };
  function render() {
    const safe = editable && !context().dirty && !context().saving && !context().loading;
    view.render({ canStart: Boolean(identity && safe && overview?.can_build && !busy && !ACTIVE.has(job?.status)),
      canRefresh: Boolean(identity && !busy), active: busy || ACTIVE.has(job?.status),
      message: error || (!safe ? '请先保存校正并等待当前操作完成。' : job?.reason_code ? REASONS[job.reason_code] || job.reason_code
        : ACTIVE.has(job?.status) ? `袖装候选正在构建 · ${job.step || '等待执行'}`
          : job?.status === 'blocked' ? '所有区域均被质量检查阻塞，请查看逐袖原因。'
          : job?.status === 'needs_review' ? '构建完成，请逐袖检查结果。' : overview?.can_build ? '可从已保存的区域标注重建袖装候选。' : '当前项目尚无已保存的袖装区域标注。'),
      rows: (safe && !error ? job?.result?.records || [] : []).map((r, index) => ({ ...r,
        url: r.status === 'candidate_exported' && r.download ? `${endpoint()}/jobs/${job.job_id}/download/${index}` : null })) });
  }
  function queue(token) {
    stop();
    if (!current(token) || !ACTIVE.has(job?.status)) return;
    if (++polls > 3600) { error = '状态查询已暂停；点击刷新继续查看，后台任务仍在执行。'; render(); return; }
    timer = schedule(() => { timer = null; void request(false, true); }, 2000);
  }
  async function request(create = false, poll = false) {
    if (!identity || busy) return;
    const token = generation, saved = { ...context() }, base = endpoint(); busy = true; error = ''; render();
    try {
      const url = poll ? `${base}/jobs/${job.job_id}` : base;
      const value = await hooks.apiRequest(url, create ? { method: 'POST', headers: { 'X-Autospine-Intent': 'pipeline-preview' },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha }) } : { cache: 'no-store' });
      if (!current(token)) return;
      if (create || poll) job = readSleeveJob(value, saved.projectId);
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
  function sync(model) {
    editable = model.preparationEditable;
    const next = projectIdentity(context());
    if (next !== identity) {
      generation++; stop(); identity = next; overview = job = null; busy = false; error = ''; polls = 0;
      if (identity) void request();
    }
    render();
  }
  return { element: view.element, sync, start, refresh, dispose() { generation++; stop(); identity = null; } };
}

function createView(document, callbacks) {
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const element = node('section'), title = node('h3', '袖装候选'), build = node('button', '重建袖装候选'), refresh = node('button', '刷新状态');
  const status = node('p'), rows = node('ul'); status.setAttribute('role', 'status');
  build.type = refresh.type = 'button'; build.addEventListener('click', callbacks.start); refresh.addEventListener('click', callbacks.refresh);
  element.append(title, node('p', '按已保存的手、袖布、袖口和垂布归属重建。重复构建会校验并复用已完成步骤。'), build, refresh, status, rows,
    node('p', 'Spine 4.3.26 候选；官方核心数值验证不包含 GPU 渲染与透明接缝检查，也不代表正式采用。'));
  return { element, render(model) {
    build.disabled = !model.canStart; refresh.disabled = !model.canRefresh; status.textContent = model.message;
    element.setAttribute('aria-busy', String(model.active));
    rows.replaceChildren(...model.rows.map(r => {
      const failure = r.reason_code === 'official_framebuffer_contact_failure' ? '官方接触检查未通过，已阻塞'
        : r.reason_code === 'official_core_numeric_failure' ? '官方核心数值未通过，已阻塞' : '区域检查未通过，已阻塞';
      const row = node('li', `${r.layer_id} · ${r.status === 'candidate_exported' ? '候选已导出' : failure} · ${r.runtime_status === 'passed' || r.runtime_status === 'core_passed' ? '核心数值验证通过' : '核心验证未通过或未执行'}`);
      if (r.official_framebuffer) row.append(node('p', framebufferMessage(r.official_framebuffer)));
      else row.append(node('p', contactMessage(r.software_contact)), node('p', overlapMessage(r.software_overlap)),
        node('p', framebufferMessage(null)));
      if (r.url) { const a = node('a', ' 下载候选 ZIP'); a.href = r.url; row.append(a); }
      return row;
    }));
  } };
}
