"""Offline source-image and triangle ownership editor."""
import base64
import hashlib
import json
from pathlib import Path


def render(candidate, draft, inputs, source=None):
    layers = {r['layer_id']: r for r in inputs.candidate['layers']}; images = {}
    for row in candidate['records']:
        key = row['layer_id']; raw = inputs.images[key]
        if hashlib.sha256(raw).hexdigest() != row['source_image_sha256']:
            raise ValueError('sleeve_review_image_mismatch')
        images[key] = dict(bbox=layers[key]['bbox'], url='data:image/png;base64,'+base64.b64encode(raw).decode())
    meshes = None if source is None else [dict(layer_id=r['layer_id'], component_id=r['component_id'], mesh=r['mesh'])
        for r in source['records'] if any((r['layer_id'],r['component_id']) == (c['layer_id'],c['component_id']) for c in candidate['records'])]
    payload = json.dumps([candidate, draft, images, inputs.skeleton['bones'], meshes], ensure_ascii=True, allow_nan=False).replace('<','\\u003c')
    code = (Path(__file__).resolve().parents[4]/'web/modules/sleeve-region-review.js').read_text(encoding='utf-8')
    brush = (Path(__file__).resolve().parents[4]/'web/modules/sleeve-brush.js').read_text(encoding='utf-8')
    live = '\n'.join((Path(__file__).resolve().parents[4]/'web/modules'/name).read_text(encoding='utf-8')
                     for name in ('sleeve-live-model.js', 'sleeve-live-panel.js'))
    code = brush + '\n' + '\n'.join(line for line in (live+'\n'+code).splitlines() if not line.startswith('import '))
    code = code.replace('export function ', 'function ')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>袖子区域复核</title>
<style>body{background:#14202d;color:white;font:16px system-ui;margin:20px}button,select{padding:9px;margin:4px}svg{width:100%;height:72vh;background:repeating-conic-gradient(#27323e 0% 25%,#34404d 0% 50%) 0/20px 20px;touch-action:none}nav{position:sticky;top:0;background:#14202d}a{color:#9df}</style>
<h1>袖布 / 袖口 / 手 · 区域草稿</h1><p>选择类别后在图上点击或拖动涂选三角形。灰色为不确定，绿色袖布、黄色袖口、粉色手、紫色垂布。显示完整源图层，只有网格覆盖区域可编辑。</p>
<p>自动预填仅依据骨轴位置，不证明服装语义。跨边界三角形需保留不确定并后续细分；本页不切原图、不改权重、不批准绑定。</p>
<nav><select id="region" aria-label="区域"></select><select id="role" aria-label="归属"></select><button id="suggest">填入当前区域建议</button><button id="undo">撤销</button><button id="reset">恢复初始草稿</button><button id="save">下载草稿</button><label>载入草稿<input id="load" type="file" accept=".json"></label><p id="message" role="status"></p></nav><svg aria-label="袖子归属画布"></svg>
<section id="sleeve-live" hidden><h2>标注实时动画</h2><p>左侧涂改，右侧立即更新。此处为基础骨驱动试算，不是最终袖口修正动画。</p>
<select data-motion aria-label="预览动作"><option value="hand">手部旋转 ±30°</option><option value="forearm">前臂 ±30°</option><option value="cloth">垂布 ±10°</option><option value="combined">同向组合</option><option value="opposed">反向组合</option></select>
<button data-play>播放</button><button data-setup>Setup</button><input data-time type="range" min="0" max="2" step=".005" value="0" aria-label="动画时间轴"><output>0.00 / 2.00 秒</output>
<p><label><input type="checkbox" data-compare>对比初始草稿</label><label><input type="checkbox" data-rigid>手部刚性试算</label><label><input type="checkbox" data-wire>显示网格</label></p>
<canvas width="720" height="720" aria-label="即时动画预览"></canvas><p data-status role="status"></p></section>
<style>body:has(#sleeve-live:not([hidden]))>svg{width:49%;height:70vh;vertical-align:top}#sleeve-live:not([hidden]){display:inline-block;width:49%;vertical-align:top}#sleeve-live canvas{width:100%;height:auto;background:repeating-conic-gradient(#27323e 0% 25%,#34404d 0% 50%) 0/20px 20px}#sleeve-live h2{margin-top:0}#sleeve-live [data-time]{width:55%}@media(max-width:850px){body:has(#sleeve-live:not([hidden]))>svg,#sleeve-live:not([hidden]){width:100%}}</style>
<script>'''.replace('<button id="suggest">', '<label>笔刷直径 <button id="brush-smaller" aria-label="缩小笔刷">−</button><input id="brush" type="range" min="4" max="120" value="24" step="1" aria-label="笔刷直径"><button id="brush-larger" aria-label="放大笔刷">＋</button><output id="brush-value">24 px</output></label><span>快捷键 [ / ]；笔刷触及的三角形整块涂选</span><button id="suggest">')+code+'\nmountSleeveReview(document,...'+payload+');</script></html>'
