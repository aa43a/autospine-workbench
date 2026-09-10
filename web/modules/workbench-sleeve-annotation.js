import { automationEndpoint, projectIdentity } from './workbench-automation-contract.js';
import { workbenchLayout } from './workbench-layout.js';

export function readSleeveAnnotation(value, context) {
  const review = `${automationEndpoint(context.projectId)}/sleeves/annotation/view`;
  if (value?.project_id !== context.projectId || value.source_sha256 !== context.resolvedSha || value.authority !== 'none'
    || !Number.isInteger(value.revision) || value.revision < 0 || typeof value.can_build !== 'boolean'
    || !['ready', 'stale', 'needs_preparation'].includes(value.status)
    || (value.candidate_sha256 != null && !/^[a-f0-9]{64}$/.test(value.candidate_sha256))
    || (value.review_url != null && value.review_url !== review)) throw Error('袖装标注响应无效，请刷新。');
  if (value.migration !== undefined) {
    const migration = value.migration;
    if (!migration || migration.authority !== 'none' || migration.requires_save !== true
      || ['manual_count', 'geometry_count', 'pending_count'].some(key => !Number.isSafeInteger(migration[key]) || migration[key] < 0))
      throw Error('袖装标注迁移摘要无效，请刷新。');
  }
  return value;
}

export function annotationMigrationText(migration) {
  if (!migration) return '';
  return `已保留人工标注 ${migration.manual_count} 个；几何预填 ${migration.geometry_count} 个；待处理 ${migration.pending_count} 个三角形。`
    + '仅保留源纹理和三角形几何完全一致的归属。新版本尚未保存，请打开画布复核并再次保存；保留记录不代表自动采用。';
}

export function annotationReason(reason) {
  if (reason === 'animated_source_missing' || reason === 'animated_source_unregistered' || reason?.includes('source'))
    return '请先在“绑定规划与复核 → 来源准备”准备动画来源，并完成关节复核，再创建袖装标注。';
  if (reason?.includes('joint')) return '关节来源尚未通过检查，请先完成关节复核并保存，再创建袖装标注。';
  return '袖装标注请求失败，请刷新后重试；仍失败时请检查来源准备和关节复核。';
}

export function createWorkbenchSleeveAnnotation(document, hooks, options = {}) {
  let identity = null, generation = 0, value = null, enabled = false, busy = false, error = '';
  const layout = options.view ? null : workbenchLayout(document);
  const view = options.view || createView(document, { prepare, refresh, preparation: () => layout?.showBinding('preparation'), joints: () => layout?.showBinding('joints') });
  const context = () => hooks.context();
  const safe = () => enabled && !context().dirty && !context().saving && !context().loading;
  const current = token => token === generation && identity === projectIdentity(context());
  function render() {
    view.render({ busy, canPrepare: Boolean(identity && safe() && !busy), canRefresh: Boolean(identity && !busy),
      reviewUrl: safe() && !error && value?.status === 'ready' ? value.review_url : null,
      prepared: Boolean(value?.candidate_sha256),
      migrationMessage: safe() && !error && !busy && value?.status === 'ready' ? annotationMigrationText(value.migration) : '',
      message: error || (busy ? '正在准备或读取袖装标注…' : !safe() ? '请先保存校正并等待当前操作完成。'
        : value?.migration ? '新标注版本已准备，请复核保留的归属并再次保存到项目。'
        : value?.can_build ? '区域草稿已保存，可以继续构建候选；未确定的归属仍需复核。'
          : value?.status === 'ready' ? '标注页面已准备。打开画布划分手、袖布、袖口和垂布，保存到项目后再构建。'
            : value?.status === 'stale' ? '标注来源已变化，请重新准备标注并复核。'
              : '先准备动画来源并复核关节，再创建袖装标注。') });
  }
  async function request(create = false) {
    if (!identity || busy || (create && !safe())) return;
    const token = generation, saved = { ...context() }; busy = true; error = ''; render();
    try {
      const result = await hooks.apiRequest(`${automationEndpoint(saved.projectId)}/sleeves/annotation${create ? '/prepare' : ''}`, create ? {
        method: 'POST', headers: { 'X-Autospine-Intent': 'pipeline-preview' },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha }),
      } : { cache: 'no-store' });
      if (current(token)) value = readSleeveAnnotation(result, saved);
    } catch (failure) { if (current(token)) error = annotationReason(failure.payload?.reason_code); }
    finally { if (current(token)) { busy = false; render(); } }
  }
  async function refresh() { await request(); hooks.onRefresh?.(); }
  function prepare() { return request(true); }
  function sync(model) {
    enabled = Boolean(model.preparationEditable);
    const next = projectIdentity(context());
    if (next !== identity) { generation++; identity = next; value = null; busy = false; error = ''; if (identity) void request(); }
    render();
  }
  return { element: view.element, sync, prepare, refresh, dispose() { generation++; identity = null; } };
}

function createView(document, callbacks) {
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const element = node('section'); element.className = 'project-route'; element.setAttribute('aria-label', '袖装区域标注');
  const title = node('h3', '袖装区域标注'), status = node('p'), migration = node('p'); status.setAttribute('role', 'status');
  const prepare = node('button', '创建袖装标注'), refresh = node('button', '刷新标注与构建状态');
  const preparation = node('button', '前往来源准备'), joints = node('button', '前往关节复核'), link = node('a', '打开标注画布');
  link.target = '_blank'; link.rel = 'noopener'; link.className = 'button button-secondary';
  for (const [button, handler] of [[prepare, callbacks.prepare], [refresh, callbacks.refresh], [preparation, callbacks.preparation], [joints, callbacks.joints]]) { button.type = 'button'; button.addEventListener('click', handler); }
  element.append(title, status, migration, preparation, joints, prepare, refresh, link);
  return { element, render(model) {
    status.textContent = model.message; prepare.disabled = !model.canPrepare; refresh.disabled = !model.canRefresh;
    migration.textContent = model.migrationMessage; migration.hidden = !model.migrationMessage;
    prepare.textContent = model.busy ? '处理中…' : model.prepared ? '重新准备标注' : '创建袖装标注';
    link.hidden = !model.reviewUrl; if (model.reviewUrl) link.href = model.reviewUrl; else link.removeAttribute('href');
  } };
}
