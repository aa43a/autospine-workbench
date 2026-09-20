import {createSourcePlayer} from './motion-source-player.js';
import {createTargetControls} from './motion-target-controls.js';
import {createGenerationControls} from './motion-generation-controls.js';
import {createSelectionControls} from './motion-selection-controls.js';
import {createContactControls} from './motion-contact-controls.js';

const $ = id => document.getElementById(id);
const player = createSourcePlayer($('canvas'), $('time'), $('play'), $('clock'));
const contactPanel = document.createElement('section');
$('diagnostic').closest('details').after(contactPanel);
const contactControls = createContactControls(contactPanel, $('time'));
const active = new Set(['pending', 'running']);
let timer = null, busy = false, previewToken = 0, refreshToken = 0, suspended = false;
const states = {
  pending: '等待解析', running: '处理中', succeeded: '解析完成', failed: '失败',
  canceled: '已取消', interrupted: '服务重启中断',
  outdated: '来源已变化',
};
const steps = {
  uploading: '上传原文件', queued: '已排队', verify_source: '校验源文件',
  convert_fbx: 'Blender 转换 FBX', verify_bridge: '逐帧核对源骨架',
  inspect_bvh: '构建源时间轴', compile_motion: '生成 MotionIR',
  inspect_npz: '核对 SOMA77 位置与旋转矩阵',
  verify_generator: '核对 Kimodo 模型与代码', verify_text_encoder: '检查本地文本编码器与 CUDA',
  generate_motion: 'Kimodo 正在生成动作（含模型加载）', verify_generation: '复查生成环境与输出',
  retarget: '角色重定向与局部修正', publish_candidate: '保存角色候选', runtime: '官方 Runtime 捕获',
};
const reasons = {
  motion_inferred_contact_drift: '推断支撑区间内存在踝部位移，请检查支撑假设与动作。',
  motion_clip_range_invalid: '片段至少包含两帧，且须位于源动作范围内。',
  motion_generation_unavailable: '服务端尚未配置本地 Kimodo 环境。',
  motion_generation_prompt_invalid: '请输入不超过 1000 字符的单行动作描述。',
  motion_generation_single_prompt_required: '首版支持单句动作；请用逗号连接要求，句点仅用于句尾。',
  motion_generation_duration_invalid: '时长须在 1–10 秒之间。',
  motion_generation_seed_invalid: '种子须为 0–2147483647 的整数。',
  motion_generation_steps_invalid: '生成步数须为 10–100 的整数。',
  motion_generation_failed: 'Kimodo 生成失败，参数与诊断已保存，可重试。',
  motion_generation_loader_changed: '生成器代码与已验证版本不一致，请检查服务端环境。',
  motion_generation_checkpoint_changed: '生成模型与已验证版本不一致，请检查服务端环境。',
  motion_generation_cuda_unavailable: '本地 Kimodo CUDA 环境不可用，请检查服务端 GPU。',
  motion_blender_unavailable: '尚未配置 Blender，请设置服务端 AUTOSPINE_BLENDER 后重试。',
  motion_skeleton_mapping_required: '骨架不匹配已支持映射，需要补充骨骼对应关系。',
  motion_projection_or_mapping_unsupported: '当前映射或投影未通过检查。',
  motion_decode_timeout: '解析超时，原文件保留。',
  motion_fbx_bridge_mismatch: 'FBX 转换后的骨架与源动作不一致。',
  motion_file_limit: '文件须为 16 字节至 64 MiB。',
  motion_filename_invalid: '请选择 FBX、BVH 或 Kimodo NPZ 文件。',
  motion_npz_profile_required: 'NPZ 需要明确选择 SOMA77 骨架约定和源帧率。',
  motion_npz_fps_invalid: '请输入 1–240 范围内的源帧率。',
  motion_queue_full: '已有两个任务正在处理，请完成后再导入。',
  motion_decode_failed: '解析失败，源文件和诊断已保留。',
  motion_import_interrupted: '上次解析未完成，可重新解析。',
  motion_canceled: '已停止解析，原文件保留。',
  motion_target_character_or_source_changed: '角色或动作来源已变化，请选择当前角色重新构建。',
  motion_target_deformation_needs_changes: '部分部件在动作中变形超限，可在候选预览中定位。',
  motion_target_sample_limit: '该动作超出首版角色适配的采样上限，请截取较短片段。',
  character_length_projection_collapsed: '骨段几乎朝向相机，当前视角不适合直接生成二维动作。',
  character_length_ratio_outside_preview_range: '投影缩短变化超出支持范围，需要调整视角或动作片段。',
  motion_contact_drift_needs_changes: '源标签对应的支撑期存在踝部滑移，自动修正未通过限制。',
};

function node(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

async function request(url, options = {}) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  const body = await response.json();
  if (!response.ok) throw Error(reasons[body.reason_code] || body.reason_code || '请求失败');
  return body;
}

async function preview(job) {
  const token = ++previewToken;
  player.clear();
  contactControls.clear();
  targetControls.select(job);
  selectionControls.select(job);
  $('title').textContent = job.name;
  $('details').textContent = '正在读取源动作…';
  try {
    const data = await request(`/api/motions/${job.job_id}/preview`);
    if (token !== previewToken) return;
    player.load(data);
    if (job.result.motion_status === 'compiled') void contactControls.load(job);
    const result = job.result;
    const outcome = result.motion_status === 'compiled' ? 'MotionIR 已生成，尚未适配角色。'
      : reasons[result.reason_code] || result.reason_code;
    const bridge = result.fbx_bridge?.passed ? 'FBX 与 BVH 全帧关节核对通过。' : '';
    $('details').textContent = `${result.joint_count} 骨 · ${result.frame_count} 帧 · `
      + `${result.fps.toFixed(2)} FPS · ${result.duration_seconds.toFixed(2)} 秒。${bridge}${outcome}`;
    $('diagnostic').textContent = result.diagnostic || '无映射诊断。';
  } catch (error) {
    if (token === previewToken) $('details').textContent = error.message;
  }
}

function render(data) {
  generationControls.update(data.kimodo_generation);
  $('environment').textContent = data.blender_available ? 'Blender 转换环境已配置。'
    : 'BVH 可直接解析；FBX 需要服务端配置 Blender。';
  $('jobs').replaceChildren();
  for (const job of data.jobs) {
    const item = node('article', '');
    item.className = 'job';
    item.dataset.jobId = job.job_id;
    const detail = job.reason_code ? reasons[job.reason_code] || job.reason_code : steps[job.step];
    const state = job.kind === 'adapt' && job.status === 'succeeded' ? '角色候选已生成' : states[job.status];
    const displayName = job.derivation?.source_name || job.name;
    item.append(node('strong', displayName + (job.kind === 'adapt' ? ' → ' + job.project_id
      : ' · ' + (job.view === 'side' ? '侧面' : '正面'))),
      node('p', `${state}${detail ? ' · ' + detail : ''}`));
    if (job.cancel_requested && active.has(job.status)) item.append(node('p', '正在停止解析进程…'));
    if (job.status === 'succeeded' && job.kind === 'adapt') {
      const result = job.result;
      if (result.clip) item.append(node('p', `源片段：第 ${result.clip.start_frame+1}–${result.clip.end_frame+1} 帧`));
      item.append(node('p', result.character_animation_status === 'needs_changes'
        ? '已生成诊断候选 · 存在投影或变形异常' : '已生成角色候选 · 待阶段验收'));
      item.append(node('p', `几何：${result.geometry_passed ? '通过' : '需调整'} · `
        + `Runtime：${result.runtime.status === 'needs_review' ? result.runtime.frames + ' 帧已捕获' : '环境不可用'}`));
      for (const issue of result.issues) item.append(node('p', reasons[issue.reason_code] || issue.reason_code));
      const contactStates = {unavailable_no_labels: '源动作无接触标签，未检查',
        inferred_proxy_corrected: '已采用有界修正保持源踝部静止；不代表鞋底接地',
        inferred_proxy_passed: '推断区间位移采样通过，尚未验证接触本身',
        inferred_proxy_drift: '推断区间有位移，需检查支撑假设与动作',
        inferred_support_unavailable: '未获得足够支撑推断证据',
        ankle_proxy_passed: '踝部支点检查通过', ankle_proxy_corrected: '已采用小幅根骨修正，踝部支点检查通过',
        needs_changes: '支撑期滑移需调整'};
      item.append(node('p', '接触：' + (contactStates[result.contact_status] || '尚未检查')));
      if (contactStates[result.contact_status]) {
        const contact = node('a', '查看接触检查');
        contact.href = `/api/motions/${job.job_id}/view/contact.html`;
        contact.target = '_blank'; contact.rel = 'noopener'; item.append(contact);
      }
      if (result.runtime.status === 'needs_review') {
        const link = node('a', '打开角色时间轴');
        link.href = `/api/motions/${job.job_id}/view/player.html`;
        link.target = '_blank'; link.rel = 'noopener'; item.append(link);
      }
      const download = node('a', '下载诊断候选 ZIP');
      download.href = `/api/motions/${job.job_id}/download`; download.className = 'download'; item.append(download);
    } else if (job.status === 'succeeded') {
      if (job.kind === 'generate') {
        const config = job.result.generation.parameters;
        item.append(node('p', `Kimodo · ${config.duration_seconds} 秒 · 种子 ${config.seed} · `
          + `${config.diffusion_steps} 步 · 生成来源已记录`));
        const details = node('details', '');
        details.append(node('summary', '生成参数与来源'), node('p', config.prompt),
          node('p', '模型 Kimodo-SOMA-RP-v1.1；本地离线执行；后处理关闭。'));
        const receipt = node('a', '查看本次任务记录');
        receipt.href = `/api/motions/${job.job_id}`; receipt.target = '_blank'; receipt.rel = 'noopener';
        details.append(receipt); item.append(details);
      }
      const button = node('button', '查看源动作');
      button.onclick = () => void preview(job);
      item.append(button);
      if (job.result.motion_status === 'compiled') {
        const projection = node('a', '查看投影异常');
        projection.href = `/api/motions/${job.job_id}/projection`;
        projection.target = '_blank'; projection.rel = 'noopener'; item.append(projection);
      }
      item.append(node('p', job.result.motion_status === 'compiled'
        ? 'MotionIR 已保存 · 尚未适配角色' : reasons[job.result.reason_code] || job.result.reason_code));
    }
    const action = active.has(job.status) ? 'cancel' : 'retry';
    const button = node('button', action === 'cancel' ? '取消' : job.kind === 'generate' ? '重新生成（保留旧记录）' : '重新解析');
    button.onclick = () => void mutate(job.job_id, action);
    button.disabled = busy || Boolean(job.cancel_requested && active.has(job.status));
    item.append(button);
    $('jobs').append(item);
  }
  if (!data.jobs.length) $('jobs').append(node('p', '尚未导入动作。'));
}

async function refresh() {
  clearTimeout(timer);
  const token = ++refreshToken;
  try {
    const data = await request('/api/motions');
    if (token !== refreshToken || suspended) return;
    render(data);
    const running = data.jobs.filter(job => active.has(job.status)).length;
    $('status').textContent = `共 ${data.jobs.length} 个任务；${running} 个正在处理。`;
    if (running) timer = setTimeout(refresh, 1500);
  } catch (error) {
    if (token === refreshToken && !suspended) $('status').textContent = error.message + ' 请点击刷新任务重试。';
  }
}

async function mutate(id, action) {
  if (busy) return;
  busy = true;
  let failure = null;
  try {
    await request(`/api/motions/${id}/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
      body: '{}',
    });
  } catch (error) { failure = error.message; }
  finally {
    busy = false;
    await refresh();
    if (failure) $('status').textContent = failure;
  }
}

$('file').onchange = () => { $('npz-options').hidden = !$('file').files[0]?.name.toLowerCase().endsWith('.npz'); };
$('upload').onclick = async () => {
  const file = $('file').files[0];
  if (!file || busy) return;
  if (file.size < 16 || file.size > 64 * 1024 * 1024) {
    $('status').textContent = reasons.motion_file_limit;
    return;
  }
  busy = true;
  $('upload').disabled = true;
  $('status').textContent = '正在上传…';
  let failure = null;
  try {
    const npzHeaders = file.name.toLowerCase().endsWith('.npz') ? {
      'X-Autospine-Npz-Profile': $('npz-profile').value, 'X-Autospine-Npz-Fps': $('npz-fps').value,
    } : {};
    await request('/api/motions', {
      method: 'POST', headers: {
        'Content-Type': 'application/octet-stream', 'X-Autospine-Intent': 'pipeline-preview',
        'X-Autospine-File-Name': encodeURIComponent(file.name), 'X-Autospine-Motion-View': $('view').value,
        ...npzHeaders,
      }, body: file,
    });
    $('file').value = '';
    $('npz-options').hidden = true;
  } catch (error) { failure = error.message; }
  finally {
    busy = false;
    $('upload').disabled = false;
    await refresh();
    if (failure) $('status').textContent = failure;
  }
};
$('refresh').onclick = () => void refresh();
const selectionControls = createSelectionControls(request, refresh);
const targetControls = createTargetControls(request, refresh, selectionControls);
const generationControls = createGenerationControls(request, refresh);
window.addEventListener('pagehide', () => {
  suspended = true;
  clearTimeout(timer);
  refreshToken++;
  previewToken++;
  player.clear();
});
window.addEventListener('pageshow', () => { suspended = false; void refresh(); });
