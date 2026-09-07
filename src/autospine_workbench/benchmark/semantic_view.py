"""Offline semantic review drafts; suggestions never become annotation authority."""
import base64
import hashlib
from html import escape
import json
import re

from ..resolved_project import canonical_sha256
from .semantic_draft import build_semantic_draft, validate_semantic_draft
from .semantic_candidates import VOCABULARY
from .semantic_decision import PAIRED_SEMANTICS
from .semantic_review_view import render_semantic_review_controls, REVIEW_SCRIPT

_LABELS = dict(zip(VOCABULARY, (
    "面部", "颈部", "躯干", "上臂", "前臂", "手", "大腿", "小腿", "脚",
    "上衣", "衣袖", "裙子", "裤子", "鞋", "前发", "侧发", "后发", "飘带", "武器",
)))
_REASONS = {
    "exact_name_alias": "名称命中明确词汇，仍需看图核对",
    "ambiguous_layer_name": "名称含义不明确，需人工判断",
    "unmapped_layer_name": "当前词汇尚未覆盖此名称",
    "canonical_side_requires_review": "名称的左右标记尚未确认",
    "empty_layer_review_required": "审计记录为空层，需决定如何处理",
    "hidden_layer_review_required": "审计记录为隐藏层，需检查是否保留",
    "layer_outside_canvas": "图层边界超出画布",
}


def render_semantic_review(candidate, composite_bytes, layer_images, *, draft=None):
    """Embed hash-bound evidence. The caller validates its complete source closure."""
    if candidate.get("schema") != "autospine.benchmark-semantic-candidates/v1":
        raise ValueError("benchmark_semantic_view_schema_invalid")
    if candidate.get("authority") != "none" or candidate.get("review_required") is not True \
            or any(layer.get("review_required") is not True
                                                  for layer in candidate["layers"]):
        raise ValueError("benchmark_semantic_view_authority_invalid")
    initial = build_semantic_draft(candidate) if draft is None else validate_semantic_draft(candidate, draft)
    layers = candidate["layers"]
    if set(layer_images) != {layer["layer_id"] for layer in layers}:
        raise ValueError("benchmark_semantic_view_images_invalid")
    cards = []
    for index, layer in enumerate(layers):
        url = _image_url(layer_images[layer["layer_id"]], layer["image_sha256"])
        if len(layer_images[layer["layer_id"]]) != layer["image"]["byte_size"]:
            raise ValueError("benchmark_semantic_view_image_changed")
        suggested = _LABELS.get(layer["semantic"], "未知（没有可靠建议）")
        observed = layer["observed"]
        observation = f"空层：{'是' if observed['empty'] else '否'}；可见：{'是' if observed['visible'] else '否'}"
        side_label = layer['raw_name_side'] or '未标记'
        reasons = '；'.join(_REASONS.get(code, code) for code in layer['reason_codes'])
        options = '<option value="">未知 / 尚未标注</option>' + ''.join(
            f'<option value="{escape(word, quote=True)}">{escape(_LABELS[word])}</option>' for word in VOCABULARY)
        cards.append(f'''<article class="card">
<h2>{escape(layer['name'])}</h2><p>{escape(layer['layer_id'])}</p>
<img class="checker" alt="{escape(layer['name'], quote=True)} 图层" src="{url}">
<p>PSD 画布 bbox：{escape(str(layer['bbox']))}</p><p>{escape(observation)}</p>
<p><strong>建议：</strong>{escape(suggested)}；原始名称侧别：{escape(side_label)}</p>
<p class="reasons">依据：{escape(reasons)}</p>
<label>语义草稿<select id="semantic-{index}">{options}</select></label>
<label>角色自身左右侧<select id="side-{index}"><option value="unknown">未知</option>
<option value="left">左侧</option><option value="right">右侧</option><option value="bilateral">双侧</option></select></label>
<label>是否纳入后续标注<select id="disposition-{index}"><option value="undecided">尚未决定</option>
<option value="include">纳入</option><option value="exclude">排除</option></select></label>
<label>备注（最多 1000 字，无控制字符）<input id="notes-{index}" maxlength="1000" type="text"></label>
</article>''')
    data = {"candidate_sha256": canonical_sha256(candidate), "layer_ids": [layer["layer_id"] for layer in layers],
            "vocabulary": list(VOCABULARY), "draft": initial,
            "empty_layer_ids": [row["layer_id"] for row in layers if row["observed"]["empty"]],
            "paired_semantics": sorted(PAIRED_SEMANTICS)}
    serialized = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for raw, encoded in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                         ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        serialized = serialized.replace(raw, encoded)
    replacements = {"__DATA__": serialized, "__CARDS__": ''.join(cards),
                    "__COMPOSITE__": _image_url(composite_bytes, candidate["composite_sha256"]),
                    "__CANVAS__": escape(str(candidate["canvas"])),
                    "__REVIEW__": render_semantic_review_controls(initial),
                    "__SCRIPT__": _SCRIPT.replace("/* REVIEW */", REVIEW_SCRIPT)}
    return re.sub('|'.join(replacements), lambda match: replacements[match[0]], _PAGE)


def _image_url(raw, digest):
    if type(raw) is not bytes or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("benchmark_semantic_view_png_required")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("benchmark_semantic_view_image_changed")
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


_PAGE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>图层语义复核草稿</title><style>
body{font:16px/1.6 system-ui,sans-serif;margin:24px auto;padding:0 20px;max-width:1200px;color:#182333;background:#f5f6f8}
h1{font-size:26px}h2{font-size:18px;overflow-wrap:anywhere;margin:0}.notice{padding:14px;background:#fff2d0;border-left:4px solid #b57800}
.checker{background-color:white;background-image:conic-gradient(#ddd 25%,transparent 0 50%,#ddd 0 75%,transparent 0);background-size:20px 20px}
#composite{display:block;max-width:100%;width:560px;height:460px;object-fit:contain;margin:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:20px}.card{background:white;border:1px solid #c9d0da;padding:16px;border-radius:8px;min-width:0}
.card img{width:100%;height:230px;object-fit:contain}.card p{font-size:14px;overflow-wrap:anywhere;margin:8px 0}
label{display:flex;flex-direction:column;margin-top:10px}button,select,input{font:inherit;padding:8px;border:1px solid #8796aa;border-radius:4px;min-width:0}
button{background:#185acb;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:default}.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:16px;margin:20px 0}
#status{min-height:26px;overflow-wrap:anywhere;color:#973b00}.reasons{color:#536070}
</style></head><body><h1>图层语义复核草稿</h1>
<p class="notice">建议只根据图层名称和审计信息生成。所有选择初始为空或未知，不代表批准、关节真值或发布权。请人工判断角色自身左右侧；名称中的 l/r 不会自动采用。</p>
<p>PSD 画布：__CANVAS__。bbox 为左、上、右、下，原点在左上，Y 向下。下方图层图片可能采用裁剪坐标，请结合 bbox 查看位置。</p>
<img id="composite" class="checker" alt="PSD 合成图" src="__COMPOSITE__">
<div class="toolbar"><button id="download" type="button">下载语义草稿</button>
<label>恢复同一候选的草稿<input id="restore" type="file" accept="application/json,.json"></label></div>
<p id="status" role="status" aria-live="polite"></p><div class="cards">__CARDS__</div>__REVIEW__
<script id="semantic-data" type="application/json">__DATA__</script><script>__SCRIPT__</script></body></html>'''


_SCRIPT = r'''(() => {
'use strict';
const data = JSON.parse(document.getElementById('semantic-data').textContent);
const get = id => document.getElementById(id), status = get('status');
const fields = ['semantic', 'side', 'disposition', 'notes'];
const controls = data.layer_ids.map((_, i) => Object.fromEntries(fields.map(key => [key, get(`${key}-${i}`)])));
function keys(value, expected) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
}
function validate(value) {
  if (!keys(value, ['schema','candidate_sha256','authority','records']) ||
      value.schema !== 'autospine.benchmark-semantic-draft/v1' || value.authority !== 'none' ||
      value.candidate_sha256 !== data.candidate_sha256 || !Array.isArray(value.records) ||
      value.records.length !== data.layer_ids.length) throw Error('草稿候选身份或结构不匹配');
  const byId = new Map();
  for (const row of value.records) {
    if (!keys(row, ['layer_id','semantic','side','disposition','notes']) ||
        !data.layer_ids.includes(row.layer_id) || byId.has(row.layer_id) ||
        !(row.semantic === null || data.vocabulary.includes(row.semantic)) ||
        !['left','right','bilateral','unknown'].includes(row.side) ||
        !['include','exclude','undecided'].includes(row.disposition) ||
        typeof row.notes !== 'string' || Array.from(row.notes).length > 1000 ||
        /\p{C}/u.test(row.notes)) throw Error('草稿图层记录无效');
    byId.set(row.layer_id, row);
  }
  return byId;
}
function collect() {
  const value = {schema:'autospine.benchmark-semantic-draft/v1', candidate_sha256:data.candidate_sha256,
    authority:'none', records:data.layer_ids.map((id, i) => ({layer_id:id,
      semantic:controls[i].semantic.value || null, side:controls[i].side.value,
      disposition:controls[i].disposition.value, notes:controls[i].notes.value}))};
  validate(value); return value;
}
function apply(value) {
  const rows = validate(value);
  controls.forEach((group, i) => fields.forEach(key => {group[key].value = rows.get(data.layer_ids[i])[key] ?? '';}));
  get('download').disabled = false;
}
function changed() {
  try {collect(); get('download').disabled = false; status.textContent = '有未下载的草稿更改；不会自动保存或采用。';}
  catch (error) {get('download').disabled = true; status.textContent = error.message;}
}
controls.forEach(group => Object.values(group).forEach(node => node.addEventListener('input', changed)));
get('download').addEventListener('click', () => {
  try {
    const value = collect(), url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'semantic-draft.json';
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = '草稿已下载；没有产生批准或标注真值。';
  } catch (error) {status.textContent = error.message;}
});
get('restore').addEventListener('change', async () => {
  const file = get('restore').files[0]; if (!file) return;
  try {
    if (file.size > 2 * 1024 * 1024) throw Error('草稿文件过大');
    const value = JSON.parse(await file.text()); apply(value);
    if (get('restore').dispatchEvent) get('restore').dispatchEvent(new Event('semantic-restored'));
    status.textContent = '已恢复同一候选的草稿；所有选择仍待正式复核。';
  } catch (error) {status.textContent = `恢复失败：${error.message}；当前选择未改变。`;}
  finally {get('restore').value = '';}
});
apply(data.draft);
/* REVIEW */
})();'''
