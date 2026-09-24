import {createSourcePlayer} from './motion-source-player.js';
import {createTargetControls} from './motion-target-controls.js';
import {createGenerationControls} from './motion-generation-controls.js';
import {createSelectionControls} from './motion-selection-controls.js';
import {createContactControls} from './motion-contact-controls.js';
import {appendDepthSummary} from './motion-depth-summary.js';
import {appendReadiness} from './motion-readiness.js';
import {appendTargetComparison} from './motion-target-comparison.js';
import {reconcileMotionJobs} from './motion-job-list.js';
import {appendStageReview} from './motion-stage-review.js';
import {appendViewComparison} from './motion-view-comparison.js';
import {appendRotationDetails} from './motion-rotation-details.js';
import {appendKneeDetails} from './motion-knee-details.js';
import {appendTorsoDetails} from './motion-torso-details.js';
import {appendPoseSummary} from './motion-pose-selection.js';
import {appendInlinePlayer} from './motion-inline-player.js';
import {jobAction,successorId} from './motion-job-actions.js';
import {poseErrors} from './motion-pose-errors.js';

const $ = id => document.getElementById(id);
const player = createSourcePlayer($('canvas'), $('time'), $('play'), $('clock'));
const contactPanel = document.createElement('section');
$('diagnostic').closest('details').after(contactPanel);
const contactControls = createContactControls(contactPanel, $('time'));
const active = new Set(['pending', 'running']);
let timer = null, busy = false, previewToken = 0, refreshToken = 0, suspended = false;
let focusedFragment = null;
const states = {
  pending: '等待解析', running: '处理中', succeeded: '解析完成', failed: '失败',
  canceled: '已取消', interrupted: '服务重启中断',
  outdated: '来源已变化',
};
const steps = {
  local_depth:'检查局部深度并分类异常',
  torso_projection:'应用躯干投影并检查脚部路径',
  uploading: '上传原文件', queued: '已排队', verify_source: '校验源文件',
  convert_fbx: 'Blender 转换 FBX', verify_bridge: '逐帧核对源骨架',
  inspect_bvh: '构建源时间轴', compile_motion: '生成 MotionIR',
  inspect_npz: '核对 SOMA77 位置与旋转矩阵',
  verify_generator: '核对 Kimodo 模型与代码', verify_text_encoder: '检查本地文本编码器与 CUDA',
  generate_motion: 'Kimodo 正在生成动作（含模型加载）', verify_generation: '复查生成环境与输出',
  retarget: '角色重定向与局部修正', post_contact_repair: '接触后脚部与局部变形修正', publish_candidate: '保存角色候选', runtime: '官方 Runtime 捕获',
  depth_overlap: '逐帧检查透明像素重叠与绘制顺序',
  depth_partition: '按已有归属拆分绘制区域',
  depth_refinement: '校准手臂与躯干深度',
  depth_cloth_constraints: '检查手臂与服装遮挡',
  depth_limb_constraints: '检查手臂与腿部遮挡',
  depth_ordering: '求解并检查绘制顺序',
};
const reasons = {
  ...poseErrors,
  runtime_storage_alpha_unsupported: 'Runtime 数值校验尚不支持该透明度轨道，请检查轨道兼容性；这不是源动作解析失败。',
  material_scene_skin_or_animation: '区域换图当前需要单一默认皮肤及单一动作。原候选保留。',
  material_scene_existing_order_or_slot_tracks: '该区域已有绘制顺序或插槽动画，当前换图策略不能安全合并；请保留原候选并调整合并策略。',
  material_scene_mesh_changed: '选区网格版本已变化，请在当前候选重新选择区域。',
  material_scene_mapping_invalid: '换图选区或时间区间无效，请重新保存映射。',
  material_scene_policy_unsupported: '该换图策略尚不支持，请重新选择当前支持的区域映射。',
  material_scene_slot_style: '该插槽的颜色、混合或附件状态尚不支持区域换图。',
  material_scene_name_collision: '区域换图附件名称冲突，请检查是否重复应用了换图。',
  material_candidate_identity_changed: '回交素材与当前候选身份不一致，请从当前任务重新准备素材。',
  material_candidate_bundle_changed: '回交素材完整性校验失败，请重新回交素材。',
  material_candidate_reference_changed: '候选骨架与数值参考不一致，请重建候选。',
  material_candidate_time_outside_motion: '换图区间超出动作范围，请调整起止时间。',
  material_candidate_sample_limit: '换图后的校验采样超过上限，请使用较短动作片段。',
  material_candidate_image_changed: '回交图片尺寸或格式不匹配，请使用原画布尺寸的 RGBA PNG。',
  motion_material_switch_requires_visual_review: '区域换图已生成，请检查切换瞬间和轮廓；原有几何异常继续保留。',
  motion_final_contact_drift: '最终播放时间轴仍有踝部漂移，请查看最终时间轴接触复核。',
  motion_post_contact_constraints_failed: '接触后局部修正仍有约束未满足，请在可用范围检查中定位对应部件和时间。',
  motion_source_contact_intervals_unverified: '已修正源证据充分的支撑区间；其余区间保留为异常，不代表整段接触通过。',
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
  motion_blender_unavailable: 'Blender 不可用，请检查服务端环境变量或状态目录 config/motion-tools.json，重启后重试。',
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
  motion_process_ownership_failed: '无法建立工作进程隔离，任务未启动。请检查服务运行权限后重试。',
  motion_termination_failed: '未能确认工作进程已停止，请检查后台任务后再重试。',
  motion_canceled: '任务已停止，原文件与历史记录保留。',
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
  const tool = data.blender_configuration;
  if(tool){
    const source={environment:'环境变量',state_config:'持久化配置',path:'PATH'}[tool.source]||'未知';
    const status={configured:'已配置',invalid_config:'配置文件无效',not_configured:'未配置',absolute_path_required:'需要绝对路径',executable_missing:'程序不存在'}[tool.status]||'未知';
    $('environment').textContent+=` 配置来源：${source}；${status}。`;
  }
  reconcileMotionJobs($('jobs'), data.jobs, job => {
    const item = node('article', '');
    item.className = 'job';
    item.id = job.job_id;
    item.dataset.jobId = job.job_id;
    const detail = job.reason_code ? reasons[job.reason_code] || job.reason_code : steps[job.step];
    const state = job.kind === 'adapt' && job.status === 'succeeded' ? '角色候选已生成' : states[job.status];
    const displayName = job.derivation?.source_name || job.name;
    item.append(node('strong', displayName + (job.kind === 'adapt' ? ' → ' + job.project_id
      : ' · ' + (job.view === 'side' ? '侧面' : '正面'))),
      node('p', `${state}${detail ? ' · ' + detail : ''}`));
    if (job.cancel_requested && active.has(job.status)) item.append(node('p', '正在停止任务及其子进程；确认停止后可重新执行。'));
    if(/^motion-[a-f0-9]{32}$/.test(job.retry_of?.job_id)){
      const retry=node('a',job.kind==='generate'?'查看原生成任务（本次为独立重试）':'查看原适配任务（保留原策略重试）');
      retry.href='/motions.html#'+job.retry_of.job_id;item.append(retry);
    }
    if (job.status === 'succeeded' && job.kind === 'adapt') {
      const result = job.result;
      appendPoseSummary(item,job);
      if(result.torso_projection_profile)appendTorsoDetails(item,job);
      if (result.projection) {
        const receipt = node('a', `投影偏转 ${result.projection.yaw_degrees}° · 查看依据`);
        receipt.href = `/api/motions/${job.job_id}/view/motion-projection.json`;
        receipt.target = '_blank'; receipt.rel = 'noopener'; item.append(receipt);
      }
      const inspection = appendInlinePlayer(item, job);
      appendDepthSummary(item, job, inspection);
      appendRotationDetails(item, job, inspection);
      appendKneeDetails(item, `/api/motions/${job.job_id}/view/`, result.artifact_sha256, inspection.onSeek);
      const compare=data.target_comparison_available?appendTargetComparison(item, job, request):null;
      appendReadiness(item, job, compare, inspection);
      if (data.stage_review_available) appendStageReview(item, job);
      if (result.clip) item.append(node('p', `源片段：第 ${result.clip.start_frame+1}–${result.clip.end_frame+1} 帧`));
      item.append(node('p', result.character_animation_status === 'needs_changes'
        ? '已生成诊断候选 · 存在投影或变形异常' : '已生成角色候选 · 待阶段验收'));
      item.append(node('p', `几何：${result.geometry_passed ? '通过' : '需调整'} · `
        + `Runtime：${result.runtime.status === 'needs_review' ? result.runtime.frames + ' 帧已捕获' : '环境不可用'}`));
      for (const issue of result.issues) item.append(node('p', reasons[issue.reason_code] || issue.reason_code));
      const contactStates = {unavailable_no_labels: '源动作无接触标签，未检查',
        inferred_partial_corrected: '已修正合格区间；源证据不足的区间未锁定',
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
      const handStatus = node('a', '手部侧向区间');
      handStatus.href = `/api/motions/${job.job_id}/view/hand-status.html`;
      handStatus.target = '_blank'; handStatus.rel = 'noopener'; item.append(handStatus);
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
        if (data.view_comparison_available) appendViewComparison(item, job, request, refresh);
        const projection = node('a', '查看投影异常');
        projection.href = `/api/motions/${job.job_id}/projection`;
        projection.target = '_blank'; projection.rel = 'noopener'; item.append(projection);
      }
      item.append(node('p', job.result.motion_status === 'compiled'
        ? 'MotionIR 已保存 · 尚未适配角色' : reasons[job.result.reason_code] || job.result.reason_code));
    }
    const {action,label,disabled} = jobAction(job);
    const button = node('button', label);
    button.onclick = () => void mutate(job.job_id, action);
    button.disabled = busy || disabled;
    item.append(button);
    return item;
  }, [busy, Boolean(data.stage_review_available), Boolean(data.view_comparison_available), Boolean(data.target_comparison_available)]);
  if (!data.jobs.length) $('jobs').append(node('p', '尚未导入动作。'));
  focusLinkedJob();
}

function focusLinkedJob() {
  const fragment = location.hash.slice(1);
  if (fragment === focusedFragment || !/^motion-[a-f0-9]{32}$/.test(fragment)) return;
  const card = document.getElementById(fragment);
  if (card) { card.scrollIntoView({block: 'start'}); focusedFragment = fragment; }
}
window.addEventListener('hashchange', () => { focusedFragment = null; focusLinkedJob(); });

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
  let successor = null;
  try {
    const result = await request(`/api/motions/${id}/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
      body: '{}',
    });
    if(action==='retry')successor=successorId(id,result);
  } catch (error) { failure = error.message; }
  finally {
    busy = false;
    await refresh();
    if(successor){location.hash=successor;focusedFragment=null;focusLinkedJob();
      $('status').textContent='已定位新任务；从头重新执行，原任务、候选及其复核记录保留。';}
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
