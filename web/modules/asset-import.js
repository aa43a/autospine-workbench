const KEY = 'autospine-active-psd-import';
const JOB = /^import-[a-f0-9]{32}$/;
const REASONS = {
  psd_filename_invalid: '文件名无效，请选择一个名称正常的 .psd 文件。',
  psd_file_limit: '文件为空、损坏或超过 256 MiB，请检查后重试。',
  invalid_psd_header: '文件不是受支持的 PSD。请保存为 Photoshop PSD，暂不支持 PSB。',
  psd_canvas_limit: '画布超过导入限制：单边最多 8192 像素，总像素最多 16777216。请缩小画布后重试。',
  psd_color_mode_unsupported: '请将 PSD 转为 RGB、8 位颜色后重新导入。',
  psd_layer_limit: '图层数量、图层尺寸或分组深度超限，请简化 PSD 后重试。',
  psd_layer_kind_unsupported: 'PSD 含非像素图层。请先栅格化文字、形状、智能对象等图层，再重新导入。',
  psd_no_pixel_layers: 'PSD 中没有可导入的像素图层。',
  psd_decoder_unavailable: '服务器缺少 PSD 解码依赖，请配置 psd-tools 和 Pillow 后重试。',
  psd_composite_missing: 'PSD 缺少可用合成图，请重新保存 PSD 后重试。',
  psd_layer_extent_mismatch: '图层渲染尺寸与 PSD 边界不一致，已停止导入以避免贴图偏移。请检查素材。',
  psd_alpha_limit: '图层透明区域数据超过导入限制，请缩小或简化图层后重试。',
  psd_extraction_failed: 'PSD 解码或图层提取失败，请检查文件并重新保存后重试。',
  psd_decode_failed: 'PSD 解码失败，请检查文件能否正常打开后重试。',
  psd_decode_timeout: 'PSD 解析超时，请缩小或简化文件后重试。',
  psd_queue_full: '已有导入任务正在执行，请稍后再导入。',
  psd_upload_incomplete: '上传未完成，请重新选择文件重试。',
  psd_upload_invalid: '上传内容无效，请重新选择文件重试。',
  psd_upload_headers_invalid: '上传请求格式无效，请刷新资产中心后重试。',
  psd_import_interrupted: '导入因服务中断而停止，请重新选择同一 PSD 重试。',
  psd_source_conflict: '项目来源存在冲突，已停止登记，请检查现有同源项目。',
  psd_import_failed: '导入失败，请检查文件后重试；如持续失败，请保留原因反馈排查。',
  psd_staging_exists: '临时导入目录存在冲突，请重新导入。',
  asset_import_too_large: 'PSD 超过 256 MiB，请缩小文件后重试。',
  asset_import_invalid: '文件不是有效 PSD，请重新选择。',
  asset_import_failed: 'PSD 解析失败，请检查文件能否正常打开，然后重试。',
  asset_import_interrupted: '导入任务已中断，请重新选择 PSD 再试。',
};

export function validatePsdFile(file) {
  if (!file || !/\.psd$/i.test(file.name)) throw Error('请选择一个 .psd 文件。');
  if (!file.size) throw Error('PSD 文件为空。');
  if (file.size > 256 * 1024 * 1024) throw Error('PSD 超过 256 MiB，请缩小文件后重试。');
}

export function readImportJob(job) {
  if (!JOB.test(job?.job_id) || !['pending', 'running', 'succeeded', 'failed'].includes(job.status)
    || !['queued', 'parsing', 'registering', 'complete'].includes(job.step)
    || (job.status === 'succeeded' && (typeof job.project_id !== 'string' || !job.project_id))) throw Error('导入状态响应无效，请刷新状态重试。');
  return job;
}

export function importJobMessage(job) {
  if (job.status === 'failed') return REASONS[job.reason_code] || `导入失败（${job.reason_code || 'unknown'}），请重新选择文件重试。`;
  if (job.status === 'succeeded') return '项目已就绪，可以打开工作台开始复核。同源 PSD 复用已有项目，并保留原有归档状态。';
  return { queued: '已上传，等待解析 PSD。', parsing: '正在解析图层和生成素材，耗时取决于文件大小。',
    registering: '正在登记项目，完成后会刷新资产列表。' }[job.step] || '正在完成导入。';
}

function upload(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/asset-imports');
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.setRequestHeader('X-Autospine-Intent', 'pipeline-preview');
    xhr.setRequestHeader('X-Autospine-File-Name', encodeURIComponent(file.name));
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
    xhr.onerror = () => reject(Error('上传连接中断，请重新选择文件重试。'));
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { reject(Error('上传响应无效，请重试。')); return; }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(Error(REASONS[data.reason_code] || `上传失败（HTTP ${xhr.status}），请重试。`)); return;
      }
      resolve(data);
    };
    xhr.send(file);
  });
}

export function createAssetImport(document, options = {}) {
  const mount = document.getElementById('asset-import');
  const node = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const title = node('h2', '新增 PSD 项目'), hint = node('p', '选择或拖入 RGB、8 位 PSD（最大 256 MiB）。支持像素图层；文字、形状和智能对象请先栅格化。上传后自动解析并登记项目。');
  const picker = node('input'); picker.type = 'file'; picker.accept = '.psd'; picker.setAttribute('aria-label', '选择 PSD 文件');
  const message = node('p', '选择文件后开始导入。'); message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite');
  const progress = node('progress'); progress.hidden = true; progress.setAttribute('aria-label', 'PSD 上传进度');
  const actions = node('div'); actions.className = 'actions';
  const retry = node('button', '刷新导入状态'); retry.type = 'button'; retry.hidden = true;
  const link = node('a', '打开新项目'); link.hidden = true; link.className = 'primary'; actions.append(retry, link);
  mount.append(title, hint, picker, progress, message, actions);
  const request = options.request || fetch, send = options.upload || upload;
  const schedule = options.schedule || setTimeout, unschedule = options.unschedule || clearTimeout;
  let id = null, timer = null, busy = false, finished = null;
  let storage = options.storage;
  try { storage ||= document.defaultView?.sessionStorage; } catch { /* Storage may be disabled. */ }
  const remember = value => { try { if (value) storage?.setItem(KEY, value); else storage?.removeItem(KEY); } catch { /* Persistence is optional. */ } };
  const stop = () => { if (timer !== null) unschedule(timer); timer = null; };
  function show(job) {
    stop(); message.textContent = importJobMessage(job); progress.hidden = true;
    busy = ['pending', 'running'].includes(job.status); picker.disabled = busy; retry.hidden = !busy;
    if (job.status === 'succeeded') {
      link.href = `/?project=${encodeURIComponent(job.project_id)}`; link.hidden = false;
      remember(null);
      if (finished !== job.job_id) { finished = job.job_id; options.onComplete?.(); }
    } else if (job.status === 'failed') remember(null);
    if (busy) timer = schedule(poll, 2000);
  }
  async function poll() {
    stop(); if (!id) return;
    retry.disabled = true;
    try {
      const response = await request(`/api/asset-imports/${id}`);
      if (!response.ok) throw Error(`无法查询导入状态（HTTP ${response.status}）。请点击刷新导入状态，避免重复上传。`);
      const job = readImportJob(await response.json());
      if (job.job_id !== id) throw Error('导入任务不匹配，请刷新状态。');
      show(job);
    } catch (e) { message.textContent = e.message; retry.hidden = false; }
    finally { retry.disabled = false; }
  }
  async function start(file) {
    if (busy) return;
    try { validatePsdFile(file); } catch (e) { message.textContent = e.message; picker.value = ''; return; }
    busy = true; picker.disabled = true; link.hidden = true; retry.hidden = true; stop();
    progress.hidden = false; progress.removeAttribute('value'); message.textContent = `正在上传 ${file.name}…`;
    try {
      const job = readImportJob(await send(file, (loaded, total) => {
        progress.max = total; progress.value = loaded;
        message.textContent = `正在上传 ${file.name} · ${Math.round(loaded / total * 100)}%`;
      }));
      id = job.job_id; remember(id); show(job);
    } catch (e) { busy = false; picker.disabled = false; progress.hidden = true; message.textContent = e.message; }
    finally { picker.value = ''; }
  }
  picker.addEventListener('change', () => start(picker.files?.[0]));
  mount.addEventListener('dragover', e => { e.preventDefault(); if (!busy) mount.classList.add('dragging'); });
  mount.addEventListener('dragleave', () => mount.classList.remove('dragging'));
  mount.addEventListener('drop', e => {
    e.preventDefault(); mount.classList.remove('dragging'); if (busy) return;
    if (e.dataTransfer.files.length !== 1) { message.textContent = '请一次导入一个 PSD 文件。'; return; }
    start(e.dataTransfer.files[0]);
  });
  retry.addEventListener('click', poll);
  try { const saved = storage?.getItem(KEY); if (JOB.test(saved)) { id = saved; busy = true; picker.disabled = true; poll(); } } catch { /* Storage may be disabled. */ }
  return { start, stop };
}
