"""Offline source-image and triangle ownership editor."""
import base64
import hashlib
import json
from pathlib import Path


def render(candidate, draft, inputs):
    layers = {r['layer_id']: r for r in inputs.candidate['layers']}; images = {}
    for row in candidate['records']:
        key = row['layer_id']; raw = inputs.images[key]
        if hashlib.sha256(raw).hexdigest() != row['source_image_sha256']:
            raise ValueError('sleeve_review_image_mismatch')
        images[key] = dict(bbox=layers[key]['bbox'], url='data:image/png;base64,'+base64.b64encode(raw).decode())
    payload = json.dumps([candidate, draft, images, inputs.skeleton['bones']], ensure_ascii=True, allow_nan=False).replace('<','\\u003c')
    code = (Path(__file__).resolve().parents[4]/'web/modules/sleeve-region-review.js').read_text(encoding='utf-8')
    brush = (Path(__file__).resolve().parents[4]/'web/modules/sleeve-brush.js').read_text(encoding='utf-8')
    code = brush + '\n' + '\n'.join(line for line in code.splitlines() if not line.startswith('import '))
    code = code.replace('export function ', 'function ')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>袖子区域复核</title>
<style>body{background:#14202d;color:white;font:16px system-ui;margin:20px}button,select{padding:9px;margin:4px}svg{width:100%;height:72vh;background:repeating-conic-gradient(#27323e 0% 25%,#34404d 0% 50%) 0/20px 20px;touch-action:none}nav{position:sticky;top:0;background:#14202d}a{color:#9df}</style>
<h1>袖布 / 袖口 / 手 · 区域草稿</h1><p>选择类别后在图上点击或拖动涂选三角形。灰色为不确定，绿色袖布、黄色袖口、粉色手、紫色垂布。显示完整源图层，只有网格覆盖区域可编辑。</p>
<p>自动预填仅依据骨轴位置，不证明服装语义。跨边界三角形需保留不确定并后续细分；本页不切原图、不改权重、不批准绑定。</p>
<nav><select id="region" aria-label="区域"></select><select id="role" aria-label="归属"></select><button id="suggest">填入当前区域建议</button><button id="undo">撤销</button><button id="reset">恢复初始草稿</button><button id="save">下载草稿</button><label>载入草稿<input id="load" type="file" accept=".json"></label><p id="message" role="status"></p></nav><svg aria-label="袖子归属画布"></svg>
<script>'''.replace('<button id="suggest">', '<label>笔刷直径 <button id="brush-smaller" aria-label="缩小笔刷">−</button><input id="brush" type="range" min="4" max="120" value="24" step="1" aria-label="笔刷直径"><button id="brush-larger" aria-label="放大笔刷">＋</button><output id="brush-value">24 px</output></label><span>快捷键 [ / ]；笔刷触及的三角形整块涂选</span><button id="suggest">')+code+'\nmountSleeveReview(document,...'+payload+');</script></html>'
