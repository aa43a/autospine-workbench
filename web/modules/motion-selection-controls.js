// A view creates a new source; clipping selects original frames for target bake.
export function createSelectionControls(request, refresh) {
  const $ = id => document.getElementById(id);
  let source = null, busy = false;
  $('reproject').onclick = async () => {
    if (!source || busy) return;
    busy = true; $('reproject').disabled = true;
    try {
      await request(`/api/motions/${source.job_id}/reproject`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
        body: JSON.stringify({view: $('selected-view').value}),
      });
      $('selection-status').textContent = '新视角已排队；完成后选择新版本应用到角色。原动作保留。';
      await refresh();
    } catch (error) { $('selection-status').textContent = error.message; }
    finally { busy = false; $('reproject').disabled = !source; }
  };
  for (const [button, input] of [['clip-in', 'clip-start'], ['clip-out', 'clip-end']]) {
    $(button).onclick = () => {
      if (!source) return;
      $(input).value = Math.min(source.result.frame_count, Math.max(1, Math.round(Number($('time').value)*source.result.fps)+1));
      $('clip-enabled').checked = true;
    };
  }
  return {
    select(job) {
      source = job;
      $('reproject').disabled = !source || busy;
      $('clip-in').disabled = $('clip-out').disabled = !source;
      $('clip-enabled').checked = false;
      $('clip-start').value = 1;
      $('clip-end').value = source?.result.frame_count || 2;
      $('clip-start').max = $('clip-end').max = source?.result.frame_count || 2;
      $('selected-view').value = source?.view || 'front';
      $('selection-status').textContent = source ? '裁剪用于下一次角色构建；保留起点原姿态和原始动作。' : '先选择源动作。';
    },
    clip() {
      if (!$('clip-enabled').checked) return null;
      const start = Number($('clip-start').value)-1, end = Number($('clip-end').value)-1;
      if (!source || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end >= source.result.frame_count) {
        throw Error('片段至少包含两帧，且须位于源动作范围内。');
      }
      return {start_frame: start, end_frame: end};
    },
  };
}
