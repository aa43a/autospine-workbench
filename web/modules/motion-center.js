import {createSourcePlayer} from './motion-source-player.js';
import {createTargetControls} from './motion-target-controls.js';

const $ = id => document.getElementById(id);
const player = createSourcePlayer($('canvas'), $('time'), $('play'), $('clock'));
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
  retarget: '角色重定向与局部修正', publish_candidate: '保存角色候选', runtime: '官方 Runtime 捕获',
};
const reasons = {
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
  targetControls.select(job);
  $('title').textContent = job.name;
  $('details').textContent = '正在读取源动作…';
  try {
    const data = await request(`/api/motions/${job.job_id}/preview`);
    if (token !== previewToken) return;
    player.load(data);
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
  $('environment').textContent = data.blender_available ? 'Blender 转换环境已配置。'
    : 'BVH 可直接解析；FBX 需要服务端配置 Blender。';
  $('jobs').replaceChildren();
  for (const job of data.jobs) {
    const item = node('article', '');
    item.className = 'job';
    const detail = job.reason_code ? reasons[job.reason_code] || job.reason_code : steps[job.step];
    const state = job.kind === 'adapt' && job.status === 'succeeded' ? '角色候选已生成' : states[job.status];
    item.append(node('strong', job.name + (job.kind === 'adapt' ? ' → ' + job.project_id : '')),
      node('p', `${state}${detail ? ' · ' + detail : ''}`));
    if (job.cancel_requested && active.has(job.status)) item.append(node('p', '正在停止解析进程…'));
    if (job.status === 'succeeded' && job.kind === 'adapt') {
      const result = job.result;
      item.append(node('p', result.character_animation_status === 'needs_changes'
        ? '已生成诊断候选 · 存在投影或变形异常' : '已生成角色候选 · 待阶段验收'));
      item.append(node('p', `几何：${result.geometry_passed ? '通过' : '需调整'} · `
        + `Runtime：${result.runtime.status === 'needs_review' ? result.runtime.frames + ' 帧已捕获' : '环境不可用'}`));
      for (const issue of result.issues) item.append(node('p', reasons[issue.reason_code] || issue.reason_code));
      if (result.runtime.status === 'needs_review') {
        const link = node('a', '打开角色时间轴');
        link.href = `/api/motions/${job.job_id}/view/player.html`;
        link.target = '_blank'; link.rel = 'noopener'; item.append(link);
      }
      const download = node('a', '下载诊断候选 ZIP');
      download.href = `/api/motions/${job.job_id}/download`; download.className = 'download'; item.append(download);
    } else if (job.status === 'succeeded') {
      const button = node('button', '查看源动作');
      button.onclick = () => void preview(job);
      item.append(button);
      item.append(node('p', job.result.motion_status === 'compiled'
        ? 'MotionIR 已保存 · 尚未适配角色' : reasons[job.result.reason_code] || job.result.reason_code));
    }
    const action = active.has(job.status) ? 'cancel' : 'retry';
    const button = node('button', action === 'cancel' ? '取消' : '重新解析');
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
const targetControls = createTargetControls(request, refresh);
window.addEventListener('pagehide', () => {
  suspended = true;
  clearTimeout(timer);
  refreshToken++;
  previewToken++;
  player.clear();
});
window.addEventListener('pageshow', () => { suspended = false; void refresh(); });
