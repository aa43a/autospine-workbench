"""Self-contained, non-authoritative PNG-to-PSD transform review page."""
import base64
import hashlib
from html import escape
import json
import re


def render_mapping_review(candidate, png_bytes, composite_bytes):
    """Render already validated candidate evidence without reading files or approving it."""
    if candidate.get("authority") != "none" or candidate.get("review_required") is not True:
        raise ValueError("benchmark_mapping_review_authority_invalid")
    if candidate.get("schema") != "autospine.benchmark-mapping-candidate/v1":
        raise ValueError("benchmark_mapping_review_schema_invalid")
    source = candidate["png_source"]
    png_url = _image_url(png_bytes)
    composite_url = _image_url(composite_bytes)
    if hashlib.sha256(png_bytes).hexdigest() != source["sha256"]:
        raise ValueError("benchmark_mapping_review_source_changed")
    evidence = candidate.get("evidence")
    if evidence and hashlib.sha256(composite_bytes).hexdigest() != evidence["composite_sha256"]:
        raise ValueError("benchmark_mapping_review_composite_changed")
    serialized = json.dumps(candidate, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # Script data is raw text in HTML; JSON escaping alone does not stop </script>.
    for raw, encoded in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                         ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        serialized = serialized.replace(raw, encoded)
    replacements = {
        "__SOURCE_NAME__": escape(source["path"], quote=True),
        "__PSD_NAME__": escape(candidate["psd_source"]["path"], quote=True),
        "__PNG_DATA__": png_url, "__COMPOSITE_DATA__": composite_url,
        "__CANDIDATE_JSON__": serialized,
    }
    return re.sub("|".join(replacements), lambda match: replacements[match[0]], _PAGE)


def _image_url(raw):
    if type(raw) is not bytes or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("benchmark_mapping_review_png_required")
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


_PAGE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>PNG 与 PSD 映射复核草稿</title>
<style>
body{font:16px/1.6 system-ui,sans-serif;margin:24px auto;padding:0 20px;max-width:1200px;background:#f5f6f8;color:#182333}
h1{font-size:25px}h2{font-size:19px}figure{margin:0;min-width:0}figcaption{overflow-wrap:anywhere}
.images{display:grid;grid-template-columns:1fr 1fr;gap:20px}.images img{width:100%;height:440px;object-fit:contain}
.checker{background-color:white;background-image:conic-gradient(#ddd 25%,transparent 0 50%,#ddd 0 75%,transparent 0);background-size:20px 20px;border:1px solid #b9c2cc}
canvas{display:block;width:100%;height:auto;max-width:850px}.controls{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0}
label{display:flex;flex-direction:column}input,button{font:inherit;padding:8px;border:1px solid #8c9aaa;border-radius:5px}input[type=number]{width:130px}
button{cursor:pointer;background:#fff}button.primary{background:#185acb;color:white}button:disabled{opacity:.5;cursor:default}
.notice{padding:12px 16px;border-left:4px solid #c78000;background:#fff4d7}#status{min-height:26px;color:#8f3000}
@media(max-width:650px){.images{grid-template-columns:1fr}.images img{height:300px}}
</style></head><body>
<h1>PNG 与 PSD 映射复核草稿</h1>
<p class="notice">此页面只生成坐标变换候选，不确认素材匹配，也不产生人工批准、关节真值或发布权。</p>
<div class="images">
<figure><figcaption>原始 PNG：__SOURCE_NAME__</figcaption><img id="source" class="checker" alt="原始 PNG" src="__PNG_DATA__"></figure>
<figure><figcaption>PSD 合成图：__PSD_NAME__</figcaption><img id="composite" class="checker" alt="PSD 合成图" src="__COMPOSITE_DATA__"></figure>
</div>
<h2>在 PSD 画布上对齐</h2>
<p>坐标原点在左上角，X 向右、Y 向下，单位为像素。原 PNG 映射为 x′ = scaleX × x + translateX，y′ = scaleY × y + translateY。负缩放表示镜像；缩放不可为零。</p>
<p>画布尺寸比例只是初始假设；请对照轮廓检查裁切、留白与形变。叠加透明度仅影响显示，不写入候选。</p>
<div class="controls">
<label>scaleX<input id="sx" type="number" step="any"></label>
<label>scaleY<input id="sy" type="number" step="any"></label>
<label>translateX<input id="tx" type="number" step="any"></label>
<label>translateY<input id="ty" type="number" step="any"></label>
<label>原 PNG 不透明度<input id="opacity" type="range" min="0" max="1" step="0.01" value="0.5"></label>
</div>
<canvas id="overlay" class="checker" aria-label="PSD 画布与变换后 PNG 叠加"></canvas>
<p id="status" role="status" aria-live="polite"></p>
<div class="controls"><button id="reset" type="button">重置为初始候选</button><button id="download" type="button" class="primary">下载变换草稿 JSON</button></div>
<p>下载后由命令行重新验证候选与源文件身份。文件仍需复核，本页不会写入项目。</p>
<script id="candidate-data" type="application/json">__CANDIDATE_JSON__</script>
<script>
'use strict';
const candidate = JSON.parse(document.getElementById('candidate-data').textContent);
const source = document.getElementById('source'), composite = document.getElementById('composite');
const canvas = document.getElementById('overlay'), context = canvas.getContext('2d');
const fields = ['sx','sy','tx','ty'].map(id => document.getElementById(id));
const opacity = document.getElementById('opacity'), status = document.getElementById('status');
const download = document.getElementById('download');
canvas.width = candidate.psd_source.canvas[0]; canvas.height = candidate.psd_source.canvas[1];
function values() {
  const result = fields.map(field => field.value.trim() === '' ? NaN : Number(field.value));
  if (!result.every(Number.isFinite) || result[0] === 0 || result[1] === 0) return null;
  const [sx,sy,tx,ty] = result;
  const [width,height] = candidate.png_source.canvas;
  const bounds = [1/sx,1/sy,-tx/sx,-ty/sy,tx+sx*width,ty+sy*height,
    (canvas.width-tx)/sx,(canvas.height-ty)/sy];
  return bounds.every(Number.isFinite) ? result : null;
}
function draw() {
  const v = values();
  const loaded = source.complete && source.naturalWidth > 0 && composite.complete && composite.naturalWidth > 0;
  download.disabled = !v || !loaded;
  status.textContent = !v ? '请输入有限数字，缩放不可为零；正向与逆向坐标不可溢出。' :
    (!loaded ? '图像正在加载；若加载失败，请重新生成复核页。' : '草稿尚未确认，可调整或下载。');
  context.setTransform(1,0,0,1,0,0); context.globalAlpha = 1;
  context.clearRect(0,0,canvas.width,canvas.height);
  if (!loaded) return;
  context.drawImage(composite,0,0);
  if (!v) return;
  context.setTransform(v[0],0,0,v[1],v[2],v[3]); context.globalAlpha = Number(opacity.value);
  context.drawImage(source,0,0);
  context.setTransform(1,0,0,1,0,0); context.globalAlpha = 1;
}
function reset() {
  const t = candidate.source_to_psd_transform;
  [...t.scale,...t.translation].forEach((value,index) => fields[index].value = value);
  opacity.value = '0.5'; draw();
}
fields.forEach(field => field.addEventListener('input',draw)); opacity.addEventListener('input',draw);
source.addEventListener('load',draw); composite.addEventListener('load',draw);
source.addEventListener('error',draw); composite.addEventListener('error',draw);
document.getElementById('reset').addEventListener('click',reset);
download.addEventListener('click',() => {
  const v = values(); if (!v || download.disabled) return;
  const draft = JSON.parse(JSON.stringify(candidate));
  draft.source_to_psd_transform = {scale:v.slice(0,2),translation:v.slice(2),coordinate_system:'pixel_top_left_y_down'};
  draft.basis = 'explicit_transform_draft'; draft.authority = 'none'; draft.review_required = true;
  const url = URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)+'\n'],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'mapping-transform-draft.json';
  document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
});
reset();
</script></body></html>'''
