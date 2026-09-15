import { automationEndpoint, projectIdentity } from './workbench-automation-contract.js';
import { readRouteGeometry, createRouteGeometryView } from './route-geometry-view.js';

const CHOICES = { ordinary: '普通绑定', sleeves: '袖装处理', undecided: '稍后决定' };
export function readProjectRoute(value, context) {
  if (value?.project_id !== context.projectId || value.authority !== 'none'
    || value.source_sha256 !== context.resolvedSha || !Number.isInteger(value.revision) || value.revision < 0
    || !Object.hasOwn(CHOICES, value.choice) || !Object.hasOwn(CHOICES, value.recommendation)
    || typeof value.stale !== 'boolean' || !Array.isArray(value.reasons)
    || value.reasons.some(reason => typeof reason !== 'string')) throw Error('处理路线响应无效，请刷新。');
  readRouteGeometry(value.geometry,context);
  return value;
}

export function createWorkbenchRoute(document, hooks, options = {}) {
  let identity = null, generation = 0, value = null, enabled = false, busy = false, error = '';
  const view = options.view || createView(document, { choose, refresh });
  const context = () => hooks.context();
  const editable = () => enabled && !context().dirty && !context().saving && !context().loading;
  const current = token => token === generation && identity === projectIdentity(context());
  function render() {
    view.render({ choice: value?.choice || 'undecided', recommendation: value?.recommendation || 'undecided',
      reasons: value?.reasons || [], stale: value?.stale || false, loaded: Boolean(value), automatic: Boolean(value?.default_choice),
      geometry: value?.geometry || null,
      enabled: Boolean(identity && editable() && value && !busy && !error), canRefresh: Boolean(identity && !busy),
      message: error || (busy ? '正在读取或保存处理路线…' : !editable() ? '请先保存校正并等待当前操作完成。'
        : value?.stale ? '项目来源已变化。原选择需要重新确认，建议已根据当前项目重新计算。'
          : value ? '选择只保存处理意向；不会自动批准标注或启动修复。' : '尚未读取项目路线。') });
  }
  async function request(choice) {
    if (!identity || busy || (choice && (!editable() || !value || error))) return;
    const token = generation, saved = { ...context() }, revision = value?.revision;
    busy = true; error = ''; render();
    try {
      const result = await hooks.apiRequest(`${automationEndpoint(saved.projectId)}/route`, choice ? {
        method: 'POST', headers: { 'X-Autospine-Intent': 'pipeline-preview' },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha, expected_revision: revision, choice }),
      } : { cache: 'no-store' });
      if (current(token)) value = readProjectRoute(result, saved);
    } catch (failure) {
      if (current(token)) error = failure.payload?.reason_code === 'project_route_source_conflict'
        ? '路线已在其他窗口变化，请刷新路线后重新选择。' : '路线请求失败，请刷新路线后重试。';
    } finally { if (current(token)) { busy = false; render(); } }
  }
  function refresh() { return request(); }
  function choose(choice) { if (Object.hasOwn(CHOICES, choice)) return request(choice); }
  function sync(model) {
    enabled = Boolean(model.preparationEditable);
    const next = projectIdentity(context());
    if (next !== identity) {
      generation++; identity = next; value = null; busy = false; error = '';
      if (identity) void refresh();
    }
    render();
  }
  return { element: view.element, sync, refresh, choose, dispose() { generation++; identity = null; } };
}

function createView(document, callbacks) {
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const element = node('section'); element.className = 'project-route'; element.setAttribute('aria-label', '角色处理路线');
  const title = node('h3', '角色处理路线'), summary = node('p'), reasons = node('p'), status = node('p');
  status.setAttribute('role', 'status'); const controls = node('div'), buttons = {};
  for (const [id, name] of Object.entries(CHOICES)) {
    const button = node('button', name); button.type = 'button'; button.addEventListener('click', () => callbacks.choose(id));
    controls.append(button); buttons[id] = button;
  }
  const refresh = node('button', '刷新路线'); refresh.type = 'button'; refresh.addEventListener('click', callbacks.refresh); controls.append(refresh);
  const geometry=createRouteGeometryView(document);
  element.append(title, summary, reasons, geometry.element, controls, status);
  return { element, render(model) {
    summary.textContent = model.loaded ? `自动建议：${CHOICES[model.recommendation]} · ${model.automatic ? '系统默认（可更改）' : '已保存选择'}：${CHOICES[model.choice]}${model.stale ? '（需要重新确认）' : ''}` : '正在检查角色适用的处理路线。';
    reasons.textContent = model.reasons.join('；'); status.textContent = model.message; refresh.disabled = !model.canRefresh;
    geometry.render(model.geometry);
    for (const [id, button] of Object.entries(buttons)) { button.disabled = !model.enabled; button.setAttribute('aria-pressed', String(model.loaded && !model.stale && model.choice === id)); }
  } };
}
