// A target is an exact existing character job; no SHA/path fields for operators.
import {createObliqueSelection} from './motion-oblique-selection.js';
import {createDepthSelection} from './motion-depth-selection.js';
import {createTorsoSelection} from './motion-torso-selection.js';
import {createPoseSelection} from './motion-pose-selection.js';
import {successorId} from './motion-job-actions.js';
export function createTargetControls(request, refresh, selection) {
  const $ = id => document.getElementById(id);
  const depth = createDepthSelection($('adapt'));
  const torso = createTorsoSelection($('adapt'));
  const pose = createPoseSelection($('adapt'));
  let source = null, character = null, token = 0, busy = false, comparing = false;
  const label = document.createElement('label');
  label.textContent = '相对源视角的恒定偏转（实验） ';
  const yaw = document.createElement('select'); yaw.disabled = true;
  yaw.setAttribute('aria-label', '动作投影偏转角');
  for (const value of ['', -90, -75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75, 90]) {
    const option = document.createElement('option'); option.value = String(value);
    option.textContent = value === '' ? '保留源视角' : `${value}°`;
    yaw.append(option);
  }
  label.append(yaw); $('adapt').before(label);
  const hint = document.createElement('p'); hint.className = 'hint';
  hint.textContent = '偏转将建立独立候选并重算动作、长度与遮挡；不会生成侧面贴图。修改源动作后角度会重置。';
  label.after(hint);
  const automatic = createObliqueSelection(request, yaw, hint, value => { comparing = value; enabled(); });
  let obliqueAvailable = false;
  void request('/api/motions').then(value => {
    obliqueAvailable = Boolean(value.oblique_target_available); yaw.disabled = !obliqueAvailable;
    automatic.available(obliqueAvailable && value.oblique_comparison_available);
    depth.available(Boolean(value.regional_depth_available),Boolean(value.sparse_depth_available));
    torso.available(Boolean(value.torso_projection_available));
  }).catch(() => {});
  function enabled() { $('adapt').disabled = busy || comparing || !source || !character; }
  async function selectProject() {
    const current = ++token, id = $('target-project').value;
    character = null; enabled();
    if (!id) { $('target-status').textContent = '选择已有整角色候选。'; return; }
    $('target-status').textContent = '正在检查角色来源…';
    try {
      const value = await request(`/api/projects/${encodeURIComponent(id)}/automation/character`);
      if (current !== token) return;
      if (value.job?.status === 'needs_review') {
        character = value.job;
        $('target-status').textContent = '使用当前完整角色候选；保留已确认的绑定、网格和纹理。';
      } else {
        $('target-status').textContent = '该角色还没有可用的整角色候选，请先在角色工作台完成构建。';
      }
    } catch (error) { if (current === token) $('target-status').textContent = error.message; }
    enabled();
  }
  async function loadProjects() {
    try {
      const value = await request('/api/projects');
      for (const project of value.projects) {
        const option = document.createElement('option');
        option.value = project.id; option.textContent = project.name;
        $('target-project').append(option);
      }
    } catch (error) { $('target-status').textContent = error.message; }
  }
  $('target-project').onchange = () => void selectProject();
  $('adapt').onclick = async () => {
    if (!source || !character || busy || comparing) return;
    const sourceId=source.job_id;
    busy = true; enabled();
    try {
      const body={project_id: character.project_id, character_job_id: character.job_id,
          contact_correction: $('contact-correction').checked, clip: selection.clip(),
          ...depth.selection(),
          ...torso.selection(depth.selection()),
          ...(obliqueAvailable && yaw.value !== '' ? {projection: {
            profile: 'constant-yaw-source-motion-v1', yaw_degrees: Number(yaw.value)}, ...automatic.selection()} : {})};
      Object.assign(body,pose.selection(body));
      const queued = await request(`/api/motions/${sourceId}/adapt`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
        body: JSON.stringify(body),
      });
      $('target-status').textContent = '角色动作已排队，将进行局部修正、几何检查与官方 Runtime 捕获。';
      await refresh();
      location.hash = successorId(sourceId,queued);
    } catch (error) { $('target-status').textContent = error.message; }
    finally { busy = false; enabled(); }
  };
  void loadProjects();
  return {select(job) {
    if (source?.job_id !== job?.job_id) {yaw.value = '';pose.reset();}
    source = job?.result?.motion_status === 'compiled' ? job : null;
    automatic.source(source);
    depth.source(source);
    torso.source(source);
    $('target-source').textContent = source ? `动作：${source.name}` : '先选择已生成 MotionIR 的源动作。';
    enabled();
  }};
}
