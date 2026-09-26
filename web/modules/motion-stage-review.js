import {stageSummary} from './motion-stage-summary.js';
const labels = {accepted: '阶段可接受', accepted_with_exceptions: '阶段可接受，保留异常',
  rejected: '需要调整', revoked: '撤销此前阶段结论'};
const reasons = {motion_review_revision_changed: '验收记录已被其他页面更新，请重新读取后再保存。',
  motion_review_evidence_changed: '候选检查证据已变化，请重新读取并检查。',
  motion_review_exceptions_require_acknowledgement: '仍有技术异常，请选择保留异常并填写说明。',
  motion_review_runtime_required: '当前缺少通过的 Runtime 证据，不能记录接受。'};

export function appendStageReview(item, job, {registration=null}={}) {
  if(registration!==null&&!/^[a-f0-9]{64}$/.test(registration))throw Error('关联候选身份无效');
  const button = document.createElement('button'); button.textContent = '记录 / 查看阶段验收';
  const panel = document.createElement('section'); panel.setAttribute('aria-live', 'polite');
  panel.className = 'motion-stage-review'; panel.hidden = true;
  const overview = document.createElement('p');
  overview.setAttribute('role', 'status'); overview.className = 'motion-stage-summary';
  overview.textContent = stageSummary(null, job.result.artifact_sha256);
  const collapse = document.createElement('button'); collapse.textContent = '收起验收详情';
  collapse.onclick = () => {panel.hidden = true; button.focus();};
  const endpoint = `/api/motions/${job.job_id}/`+(registration?`related-candidates/${registration}/`:'')+'stage-review';
  async function request(options) {
    const response = await fetch(endpoint, {cache: 'no-store', ...options});
    const result = await response.json();
    if (!response.ok) throw Error(reasons[result.reason_code] || result.reason_code || '验收请求失败');
    if(result.artifact_sha256!==job.result.artifact_sha256)throw Error('候选版本已变化，请重新打开。');
    if(registration&&(result.registration_sha256!==registration||result.readiness?.registration_sha256!==registration))
      throw Error('关联记录已变化，请重新打开此版本。');
    return result;
  }
  function render(state) {
    overview.textContent = stageSummary(state, job.result.artifact_sha256);
    panel.replaceChildren();
    const status = document.createElement('p');
    status.textContent = state.current
      ? `r${state.revision} · ${labels[state.current.decision]}${state.current_applies ? '' : '（证据已变化，需重新复核）'}。${state.current.notes}`
      : '尚未记录本候选的阶段验收。';
    const note = document.createElement('p');
    note.textContent = '请先查看当前角色时间轴。这里只记录视觉阶段结论；投影、接触、几何和遮挡检查保持原结果，不代表发布许可。';
    if(registration)note.append(' 此结论只属于当前改进版本及这次证据登记；不替换原任务，也不转移到其他改进版本。');
    const technical=document.createElement('details');
    const technicalTitle=document.createElement('summary');technicalTitle.textContent='当前版本的检查范围';technical.append(technicalTitle);
    for(const stage of state.readiness.stages||[]){
      const line=document.createElement('p');line.textContent=`${stage.stage}：${({sampled_pass:'限定采样通过',needs_changes:'需处理',unmeasured:'尚未验证'})[stage.status]||'未知'}。${stage.explanation||''}`;
      technical.append(line);
    }
    if(['legacy_empty_projection_fields','legacy_empty_diagnostic_fields'].includes(state.evidence_match))note.append(' 已核实仅有已知诊断字段新增且为空，其余证据与原验收摘要完全一致，沿用原人工结论；没有新增验收记录。');
    const decision = document.createElement('select'); decision.setAttribute('aria-label', '阶段验收结论');
    decision.add(new Option('选择验收结论', ''));
    for (const [value, text] of Object.entries(labels)) {
      const option = new Option(text, value);
      if (value === 'accepted' && state.readiness.status !== 'stage_review') option.disabled = true;
      decision.add(option);
    }
    const notes = document.createElement('textarea'); notes.maxLength = 4000;
    notes.setAttribute('aria-label', '验收说明'); notes.placeholder = '异常位置、动作时间及可接受范围；保留异常或退回时必填。';
    const confirmation = document.createElement('label');
    const checked = document.createElement('input'); checked.type = 'checkbox';
    confirmation.append(checked, '我已检查当前候选，并了解检查中保留的异常。');
    const save = document.createElement('button'); save.textContent = '保存阶段结论';
    save.disabled = true;
    const update = () => { save.disabled = !decision.value || !checked.checked
      || ['accepted_with_exceptions', 'rejected'].includes(decision.value) && !notes.value.trim(); };
    decision.onchange = update; checked.onchange = update; notes.oninput = update;
    const feedback = document.createElement('p'); feedback.setAttribute('role', 'status');
    save.onclick = async () => {
      save.disabled = true; button.disabled = true; panel.inert = true;
      try {
        const next = await request({method: 'POST', headers: {'Content-Type': 'application/json',
          'X-Autospine-Intent': 'pipeline-preview'}, body: JSON.stringify({
            artifact_sha256: state.artifact_sha256, evidence_sha256: state.evidence_sha256,
            ...(registration?{registration_sha256:registration}:{}),
            expected_revision: state.revision, decision: decision.value, notes: notes.value})});
        render(next);
        window.dispatchEvent(new CustomEvent(registration?'motion-related-review-saved':'motion-stage-review-saved',
          {detail:{jobId:job.job_id,...(registration?{registration}: {})}}));
      } catch (error) {
        feedback.textContent = error.message;
        overview.textContent = '保存未完成，当前状态需重新核对：' + error.message;
        update();
      }
      finally { button.disabled = false; panel.inert = false; }
    };
    const history = document.createElement('details');
    const title = document.createElement('summary'); title.textContent = `历史记录（${state.history.length}）`; history.append(title);
    for (const row of state.history.slice().reverse()) {
      const p = document.createElement('p'); p.textContent = `r${row.revision} · ${row.created_at} · ${labels[row.decision]} · ${row.notes}`;
      history.append(p);
    }
    panel.append(collapse, status, note, technical, decision, notes, confirmation, save, feedback, history);
  }
  button.onclick = async () => {
    button.disabled = true; panel.inert = true; panel.hidden = false;
    overview.textContent = '正在核对当前候选的技术状态与阶段结论…';
    try { render(await request()); }
    catch (error) { panel.textContent = error.message; overview.textContent = '当前状态未核实：' + error.message; }
    finally { button.disabled = false; panel.inert = false; }
  };
  item.append(overview, button, panel);
}
