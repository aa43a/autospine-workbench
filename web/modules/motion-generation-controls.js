// Generation shares the motion journal, cancellation, and source preview.
export function createGenerationControls(request, refresh) {
  const $ = id => document.getElementById(id);
  let busy = false, configured = false;
  const enabled = () => { $('generate').disabled = busy || !configured; };
  $('generation-form').onsubmit = async event => {
    event.preventDefault();
    if (busy || !configured) return;
    busy = true; enabled();
    $('generation-status').textContent = '正在创建生成任务…';
    try {
      await request('/api/motions/generate', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
        body: JSON.stringify({prompt: $('prompt').value, duration_seconds: Number($('duration').value),
          seed: Number($('seed').value), diffusion_steps: Number($('steps').value), view: $('generation-view').value}),
      });
      $('generation-status').textContent = '已排队。下方任务卡显示当前阶段；完成后可查看源动作并应用到角色。';
      await refresh();
    } catch (error) { $('generation-status').textContent = error.message; }
    finally { busy = false; enabled(); }
  };
  return {update(state) {
    configured = state === 'configured'; enabled();
    $('generation-environment').textContent = configured
      ? '本地生成环境已配置；运行时会检查模型、文本编码器和 CUDA。'
      : '本地生成环境未配置；仍可导入现有动作文件。';
  }};
}
