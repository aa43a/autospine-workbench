"""Explicit semantic review requests bound to the page's original draft."""
from ..resolved_project import canonical_sha256


def render_semantic_review_controls(draft):
    return CONTROLS.replace("__DRAFT_SHA__", canonical_sha256(draft))


CONTROLS = '''<section aria-labelledby="semantic-review-title">
<h2 id="semantic-review-title">正式语义复核请求</h2>
<p>完成草稿后请先下载，再使用该草稿重新生成页面。此处仅下载请求，命令行显式确认并核验源文件后才记录决定。</p>
<p>接受要求每层明确纳入或排除；排除须说明原因；空层不能纳入；纳入须选择语义，成对肢体须标注侧别。</p>
<label>复核结果<select id="semantic-choice"><option value="">请选择</option><option value="accept">接受</option><option value="reject">拒绝</option></select></label>
<label>复核人<input id="semantic-reviewer" maxlength="128" autocomplete="off"></label>
<label>复核说明<input id="semantic-reason" maxlength="2000" autocomplete="off"></label>
<label><input id="semantic-check-identity" type="checkbox">已核对图层素材身份</label>
<label><input id="semantic-check-semantics" type="checkbox">已逐层检查语义和纳入决定</label>
<label><input id="semantic-check-sides" type="checkbox">已检查角色自身左右侧</label>
<p id="semantic-review-status" role="status" aria-live="polite"></p>
<button id="semantic-review-download" type="button" disabled>下载语义复核请求</button>
<span id="semantic-review-binding" data-draft-sha="__DRAFT_SHA__" hidden></span>
</section>'''


# Runs inside semantic_view's closure, using its validated collect() and data.
REVIEW_SCRIPT = r'''
(() => {
if (!get('semantic-choice')) return;
const reviewChoice = get('semantic-choice'), reviewer = get('semantic-reviewer');
const reviewReason = get('semantic-reason'), reviewSave = get('semantic-review-download');
const reviewChecks = ['identity','semantics','sides'].map(name => get('semantic-check-'+name));
function sameDraft(value) {
  const initial = new Map(data.draft.records.map(row => [row.layer_id,row]));
  return value.records.every(row => fields.every(key => row[key] === initial.get(row.layer_id)[key]));
}
function reviewProblem() {
  const value = collect();
  if (!sameDraft(value)) return '草稿已修改；请先下载草稿并重新生成页面，再提交复核请求。';
  if (!['accept','reject'].includes(reviewChoice.value)) return '请选择复核结果。';
  if (!reviewer.value.trim() || [...reviewer.value].length > 128 || /\p{C}/u.test(reviewer.value)) return '请填写有效复核人。';
  if (!reviewReason.value.trim() || [...reviewReason.value].length > 2000 || /\p{C}/u.test(reviewReason.value)) return '请填写有效复核说明。';
  if (reviewChoice.value === 'reject') return '';
  if (!reviewChecks.every(node => node.checked)) return '接受前请完成三项检查。';
  if (![...document.querySelectorAll('.checker')].every(img => img.complete && img.naturalWidth > 0)) return '证据图片尚未完整加载。';
  for (const row of value.records) {
    if (row.disposition === 'undecided') return '每层须明确纳入或排除。';
    if (row.disposition === 'exclude') {if (!row.notes.trim()) return '排除图层须填写备注。'; continue;}
    if (data.empty_layer_ids.includes(row.layer_id)) return '空层不能纳入。';
    if (!row.semantic) return '纳入图层须选择语义。';
    if (data.paired_semantics.includes(row.semantic) && row.side === 'unknown') return '成对肢体须标注侧别。';
  }
  return '';
}
function updateReview() {
  let error; try {error = reviewProblem();} catch (problem) {error = problem.message;}
  reviewSave.disabled = Boolean(error);
  get('semantic-review-status').textContent = error || '可下载请求；尚未记录任何决定。';
}
[reviewChoice,reviewer,reviewReason,...reviewChecks,...controls.flatMap(group => Object.values(group))]
  .forEach(node => {node.addEventListener('input',updateReview); node.addEventListener('change',updateReview);});
document.querySelectorAll('.checker').forEach(img => {
  img.addEventListener('load',updateReview); img.addEventListener('error',updateReview);
});
get('restore').addEventListener('semantic-restored',updateReview);
reviewSave.addEventListener('click',() => {
  updateReview(); if (reviewSave.disabled) return;
  const request = {schema:'autospine.benchmark-semantic-review-request/v1',authority:'none',
    candidate_sha256:data.candidate_sha256,draft_sha256:get('semantic-review-binding').dataset.draftSha,
    reviewer:reviewer.value.trim(),action:reviewChoice.value,reason:reviewReason.value.trim(),
    checks:{layer_identity:reviewChecks[0].checked,semantics_checked:reviewChecks[1].checked,sides_checked:reviewChecks[2].checked}};
  const url = URL.createObjectURL(new Blob([JSON.stringify(request,null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'semantic-review-request.json';
  document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
});
updateReview();
})();
'''
