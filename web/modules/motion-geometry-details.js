import {describeShape} from './motion-shape-evidence.js';
import {appendRepairDraft} from './motion-repair-draft.js';
import {appendRepairFeasibility} from './motion-repair-feasibility.js';
import {diagnosticPanel} from './motion-diagnostic-panel.js';
const node = (tag, text) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
};

export function appendGeometryDetails(parent, job, onSeek, onInspect) {
  const base = `/api/motions/${encodeURIComponent(job.job_id)}/view/`;
  diagnosticPanel(parent, {label:'查看变形区域与处理方案',
    load:async()=>{
      const response = await fetch(base + 'geometry-details.json', {cache:'no-store'});
      const report = await response.json();
      if (!response.ok) throw Error(report.reason_code || '区域检查失败');
      if (report.artifact_sha256 !== job.result.artifact_sha256)
        throw Error('候选版本已变化，请刷新任务');
      return report;
    },
    render:(panel,report)=>{
      if (report.status === 'unavailable') {
        panel.append(node('p', '当前候选缺少定位证据，请重建；原检查状态保持不变。'));
        return;
      }
      panel.append(node('p', '这里显示原纹理上的失败网格。投影缩短、权重或素材轮廓均可能造成异常；不能仅凭面积比决定补图。'));
      for (const row of report.rows) renderRow(panel, row, base, onSeek, onInspect, job);
      if (!report.rows.length) panel.append(node('p', '当前报告没有几何失败记录。'));
    }
  });
}

function renderRow(panel, row, base, onSeek, onInspect, job) {
  const section = node('section');
  section.append(node('h4', `${row.slot}${row.attachment ? ' / '+row.attachment : ''} · ${row.animation}`));
  section.append(node('p', `${row.failed_area_triangles} 个面积异常三角形；展示 ${row.shown} 个极值事件${row.truncated ? '（其余保留在原检查中）' : ''}。`));
  panel.append(section);
  if (!row.details.length) {
    section.append(node('p', '本记录没有面积异常，需继续检查边长或其他几何失败；不视为通过。'));
    return;
  }
  const select = node('select'); select.setAttribute('aria-label', `${row.slot} 异常区域`);
  row.details.forEach((detail, index) => {
    const option = node('option', `三角形 ${detail.triangle} · ${detail.reason === 'area_expansion' ? '扩张' : '压缩/翻转'} · ${detail.time.toFixed(3)} 秒`);
    option.value = String(index); select.append(option);
  });
  const canvas = node('canvas'); canvas.style.cssText = 'display:block;max-width:100%;max-height:480px;background:#263442';
  canvas.setAttribute('aria-label', '原始纹理及异常三角形位置');
  const canInspect = onInspect && !row.attachment;
  const detailText = node('p'); const seek = node('a', canInspect ? '定位时间并高亮动作区域' : '定位到此动作时刻');
  const shapeText = node('p');shapeText.setAttribute('aria-label','投影与局部形状对照');
  const image = new Image();
  const draw = () => {
    const detail = row.details[Number(select.value)];
    shapeText.textContent=describeShape(detail.shape_evidence);
    detailText.textContent = `此时面积/原姿态：${detail.setup_ratio.toFixed(3)}；投影参考/原姿态：${detail.projected_reference_ratio?.toFixed(3) ?? '不可用'}。影响骨骼：${detail.bones.join('、')}。`;
    if (Number.isFinite(detail.without_deform_setup_ratio)) {
      detailText.append(` 同时刻移除局部 deform 后：${detail.without_deform_setup_ratio.toFixed(3)}；修正造成的面积比变化：${detail.deform_area_delta_ratio.toFixed(3)}（正值表示面积增加，未必更自然）。`);
    }
    seek.href = base + `player.html?time=${detail.time}`;
    if (onSeek) seek.onclick = event => {
      event.preventDefault();
      try {
        onSeek(detail.time);
        if(canInspect&&onInspect(row.slot,detail.triangle,row.animation)===false)
          throw Error('高亮未就绪，请等待匹配候选加载后重试');
      } catch(error) {detailText.append(' 定位失败：'+error.message);}
    };
    else {seek.target = '_blank'; seek.rel = 'noopener';}
    if (!image.naturalWidth) return;
    const scale = Math.min(1, 900 / Math.max(image.naturalWidth, image.naturalHeight));
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    detail.texture_uv.forEach(([u,v], i) => ctx[i ? 'lineTo' : 'moveTo'](u * canvas.width, v * canvas.height));
    ctx.closePath(); ctx.fillStyle = '#ff334466'; ctx.fill();
    ctx.strokeStyle = '#ffcc00'; ctx.lineWidth = 2; ctx.stroke();
  };
  image.onload = draw;
  image.onerror = () => {detailText.append(' 原纹理加载失败。');};
  section.append(select, canvas, detailText, shapeText, seek, node('p', row.note),
    node('p', '处理顺序：先同帧核对源动作的方向和前后关系；方向正确后再检查权重、分区及局部形状。区域换图只替换选区纹理，保留原网格与动作，不能消除翻转、压缩或错误的屈膝方向。所有修正另建候选，保留原结果。'));
  draw(); image.src = row.texture;
  if(row.repair_scope === 'active_attachment_read_only') {
    section.append(node('p','此记录使用独立姿态附件；可查看贴图定位和动作时间。当前固定网格编辑器不支持修改此附件，原失败记录保留。'));
    select.onchange=draw;
    return;
  }
  appendRepairFeasibility(section,job,row,onSeek);
  const changed=appendRepairDraft(section,job,row,()=>row.details[Number(select.value)]);
  select.onchange=()=>{draw();changed();};
}
