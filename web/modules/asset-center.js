import { createAssetImport } from './asset-import.js';
import { sleeveProgress } from './sleeve-progress.js';

const LABELS = { active: '进行中', archived: '已归档', trashed: '回收站' };

export function assetTaskMessage(task) {
  if (!task || !['pending', 'running'].includes(task.status)) return null;
  const kinds = { sleeves: '袖装修复', preparation: '来源准备', animation: '动画候选', preview: 'Spine 预览' };
  const kind = kinds[task.kind] || '项目任务';
  if (task.status === 'pending') return `${kind} · 已排队`;
  return `${kind} · ${task.kind === 'sleeves' ? sleeveProgress(task).label : '正在处理'}`;
}

export function filterAssets(projects, lifecycle, query) {
  const needle = query.trim().toLocaleLowerCase();
  return projects.filter(p => p.lifecycle === lifecycle
    && `${p.name} ${p.id}`.toLocaleLowerCase().includes(needle));
}

export function assetMutation(project, action, name) {
  if (!Number.isInteger(project.revision) || project.revision < 0) throw Error('项目版本无效，请刷新资产。');
  if (!['rename', 'archive', 'trash', 'restore'].includes(action)) throw Error('项目操作无效。');
  const payload = { action, expected_revision: project.revision };
  if (action === 'rename') {
    if (!name?.trim()) throw Error('请输入项目名称。');
    payload.name = name.trim();
  }
  return payload;
}

export function createAssetCenter(document, request = fetch) {
  const get = id => document.getElementById(id);
  const node = (tag, text = '', cls = '') => {
    const el = document.createElement(tag); el.textContent = text; el.className = cls; return el;
  };
  let projects = [], lifecycle = 'active', busy = false;
  const error = message => { get('error').textContent = message; get('error').hidden = !message; };
  async function json(url, options) {
    const response = await request(url, options);
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      if (failure.reason_code === 'asset_job_running') throw Error('项目正在执行任务，请等待任务结束后再归档或移入回收站。');
      if (response.status === 409) throw Error('项目已在其他窗口变化，请刷新资产后重试。');
      throw Error(`操作失败（HTTP ${response.status}），请刷新后重试。`);
    }
    return response.json();
  }
  async function refresh() {
    if (busy) return;
    busy = true; error(''); render(); get('status').textContent = '正在加载资产…';
    try {
      const data = await json('/api/asset-library');
      if (!Array.isArray(data.projects)) throw Error('资产列表响应无效。');
      projects = data.projects;
    } catch (e) { error(e.message); }
    finally { busy = false; render(); }
  }
  async function mutate(project, action, name) {
    if (busy) return;
    let payload;
    try { payload = assetMutation(project, action, name); } catch (e) { error(e.message); return; }
    busy = true; error(''); setDisabled(); get('status').textContent = '正在保存项目状态…';
    try {
      await json(`/api/asset-library/${encodeURIComponent(project.id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview' },
        body: JSON.stringify(payload),
      });
      const data = await json('/api/asset-library');
      if (!Array.isArray(data.projects)) throw Error('状态已保存，但刷新失败，请手动刷新资产。');
      projects = data.projects;
    } catch (e) { error(e.message); }
    finally { busy = false; render(); }
  }
  function button(label, handler) {
    const b = node('button', label); b.type = 'button'; b.disabled = busy;
    b.addEventListener('click', handler); return b;
  }
  function card(p) {
    const item = node('article', '', 'card'), img = node('img');
    img.src = `/api/projects/${encodeURIComponent(p.id)}/composite`; img.alt = `${p.name} 角色预览`; img.loading = 'lazy';
    const imageBox = node('div', '', 'thumbnail'); imageBox.append(img);
    img.addEventListener('error', () => imageBox.replaceChildren(node('span', '缩略图暂不可用')));
    const info = node('div', '', 'card-info'); info.append(node('span', LABELS[p.lifecycle], 'badge'), node('h2', p.name), node('p', p.id, 'project-id'));
    if (Number.isInteger(p.layer_count)) info.append(node('p', `${p.layer_count} 个源图层`));
    const taskMessage = assetTaskMessage(p.current_task);
    if (taskMessage) info.append(node('p', taskMessage, 'task-status'));
    info.append(node('p', p.workflow_status === 'needs_review' ? '项目仍有待复核内容，请进入工作台查看。'
      : p.workflow_status === 'ready' ? '素材状态就绪；动画和导出结果请进入工作台检查。' : '进入工作台查看当前处理阶段。'));
    const actions = node('div', '', 'actions');
    if (p.lifecycle !== 'trashed') {
      const open = node('a', '打开工作台', 'primary'); open.href = `/?project=${encodeURIComponent(p.id)}`; actions.append(open);
    }
    if (p.lifecycle === 'active') actions.append(button('归档', () => mutate(p, 'archive')));
    else actions.append(button('恢复项目', () => mutate(p, 'restore')));
    if (p.lifecycle !== 'trashed') actions.append(button('移入回收站', () => mutate(p, 'trash')));
    info.append(actions);
    if (p.lifecycle !== 'trashed') {
      const details = node('details'), summary = node('summary', '重命名'), form = node('form');
      const label = node('label', '项目名称'), input = node('input'); input.value = p.name; input.required = true; input.maxLength = 120;
      label.append(input); const save = node('button', '保存名称'); save.type = 'submit'; save.disabled = busy;
      form.append(label, save); form.addEventListener('submit', e => { e.preventDefault(); mutate(p, 'rename', input.value); });
      details.append(summary, form); info.append(details);
    }
    item.append(imageBox, info); return item;
  }
  function setDisabled() {
    for (const el of document.querySelectorAll('#projects button,#projects input,#filters button,#refresh,#search')) el.disabled = busy;
  }
  function render() {
    get('filters').replaceChildren(...Object.entries(LABELS).map(([key, label]) => {
      const b = button(`${label} ${projects.filter(p => p.lifecycle === key).length}`, () => { lifecycle = key; render(); });
      b.setAttribute('aria-pressed', String(key === lifecycle)); return b;
    }));
    const rows = filterAssets(projects, lifecycle, get('search').value);
    get('projects').replaceChildren(...(rows.length ? rows.map(card) : [node('p', '此分类下没有匹配项目。', 'empty')]));
    get('status').textContent = `${LABELS[lifecycle]} · 显示 ${rows.length} 个项目`;
    setDisabled();
  }
  get('refresh').addEventListener('click', refresh); get('search').addEventListener('input', render);
  if (get('asset-import')) createAssetImport(document, { onComplete: refresh });
  refresh(); return { refresh };
}

if (typeof document !== 'undefined' && document.getElementById('projects')) createAssetCenter(document);
