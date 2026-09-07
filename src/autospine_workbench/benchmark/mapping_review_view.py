"""Explicit offline mapping review requests; the page never records a decision."""

from ..resolved_project import canonical_sha256


def render_review_controls(candidate):
    return _CONTROLS.replace("__CANDIDATE_SHA__", canonical_sha256(candidate))


_CONTROLS = '''<section aria-labelledby="review-title">
<h2 id="review-title">提交映射复核请求</h2>
<p>请检查两张图是否为同一角色、轮廓与坐标是否对齐，以及镜像是否符合实际。
此处只下载请求；命令行显式确认并重新验证源文件后才记录复核决定。不会授予发布权。</p>
<p>上方校准误差仅对应生成页面时的候选。修改变换不会重新计算误差；
请先下载变换草稿并重新生成复核页，再复核新候选。</p>
<div class="controls">
<label>复核结果<select id="review-choice"><option value="">请选择复核结果</option>
<option value="accept">接受此映射</option><option value="reject">拒绝此映射</option></select></label>
<label>复核人<input id="reviewer" type="text" maxlength="128" autocomplete="off"></label>
<label>复核说明（必填）<input id="review-reason" type="text" maxlength="2000" autocomplete="off"></label>
</div>
<div class="controls">
<label><input id="review-same-character" type="checkbox">已确认是同一角色与素材</label>
<label><input id="review-coordinate-alignment" type="checkbox">已检查坐标和轮廓对齐</label>
<label><input id="review-mirror-checked" type="checkbox">已检查镜像方向</label>
</div>
<p id="review-status" role="status" aria-live="polite"></p>
<button id="review-download" type="button" disabled>下载复核请求</button>
<span id="review-binding" hidden data-candidate-sha="__CANDIDATE_SHA__"></span>
</section>'''


REVIEW_SCRIPT = r'''
(() => {
  const binding = document.getElementById('review-binding');
  if (!binding) return;
  const choice = document.getElementById('review-choice'), reviewer = document.getElementById('reviewer');
  const reason = document.getElementById('review-reason'), message = document.getElementById('review-status');
  const save = document.getElementById('review-download');
  const checks = ['same-character','coordinate-alignment','mirror-checked']
    .map(id => document.getElementById('review-'+id));
  const original = [...candidate.source_to_psd_transform.scale,...candidate.source_to_psd_transform.translation];
  function problem() {
    if (!['accept','reject'].includes(choice.value)) return '请选择复核结果；不会自动接受候选。';
    if (!reviewer.value.trim() || [...reviewer.value.trim()].length > 128 || /\p{C}/u.test(reviewer.value))
      return '请填写复核人（最多 128 字符，不含控制字符）。';
    if (!reason.value.trim() || [...reason.value.trim()].length > 2000 || /\p{C}/u.test(reason.value))
      return '请填写复核说明（最多 2000 字符，不含控制字符）。';
    if (choice.value === 'reject') return '';
    const v = values();
    if (!v || v.some((value,index) => value !== original[index]))
      return '变换已修改。请先下载变换草稿并重新生成复核页，再接受新候选。';
    if (!(source.complete && source.naturalWidth > 0 && composite.complete && composite.naturalWidth > 0))
      return '两张证据图加载完成后才能接受映射。';
    if (!checks.every(check => check.checked)) return '接受映射前请逐项完成三项检查。';
    return '';
  }
  function update() {
    const error = problem(); save.disabled = Boolean(error);
    message.textContent = error || '可以下载复核请求；尚未记录任何复核决定。';
  }
  [choice,reviewer,reason,...checks,...fields].forEach(field => {
    field.addEventListener('input',update); field.addEventListener('change',update);
  });
  document.getElementById('reset').addEventListener('click',update);
  [source,composite].forEach(image => {
    image.addEventListener('load',update); image.addEventListener('error',update);
  });
  save.addEventListener('click',() => {
    update(); if (save.disabled) return;
    const request = {schema:'autospine.benchmark-mapping-review-request/v1',
      candidate_sha256:binding.dataset.candidateSha,authority:'none',reviewer:reviewer.value.trim(),
      action:choice.value,reason:reason.value.trim(),checks:{same_character:checks[0].checked,
        coordinate_alignment:checks[1].checked,mirror_checked:checks[2].checked}};
    const url = URL.createObjectURL(new Blob([JSON.stringify(request,null,2)+'\n'],{type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mapping-review-request.json';
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  update();
})();
'''
