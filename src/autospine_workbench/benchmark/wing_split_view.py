"""Offline mask editor with original target and optional wing composition."""
import base64
import json
from hashlib import sha256
from .wing_split_draft import initial,validate
from .wing_split_script import SCRIPT


def render(source,files,draft=None):
    draft=validate(source,draft) if draft is not None else initial(source)
    if any(sha256(files[n]).hexdigest()!=digest for n,digest in source['files'].items()):raise ValueError('wing_split_file_changed')
    regions={r['id']:r for r in source['regions']};x,y=regions['topwear']['setup_vertices_xy'][0]
    def image(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode()
    references=[]
    for name,region in regions.items():
        if name=='topwear':continue
        px,py=region['setup_vertices_xy'][0]
        references.append(dict(x=px-x,y=py-y,image=image(files['editor/images/'+name+'.png'])))
    state=dict(draft=draft,image=image(files['editor/images/topwear.png']),references=references,
      hints=[[a-x,b-y,c-x,d-y] for a,b,c,d in (r['canvas_bbox'] for r in source['review_queue'])])
    payload=json.dumps(state,ensure_ascii=True).replace('<','\\u003c')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>上衣／翼片拆分遮罩</title><style>body{{font:17px/1.6 system-ui;margin:24px;color:#243448;background:#f4f6f8}}button,select,input{{margin:5px;padding:8px}}.toolbar{{position:sticky;top:0;background:#f4f6f8;z-index:2;padding:6px}}main{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}section{{min-width:0}}.viewport{{overflow:auto;max-height:75vh;background:repeating-conic-gradient(#eee 0% 25%,#fff 0% 50%) 0/20px 20px}}canvas{{display:block;height:auto;touch-action:none}}#edit{{cursor:crosshair}}h2{{font-size:19px}}@media(max-width:800px){{main{{grid-template-columns:1fr}}}}</style>
<h1>上衣／翼片拆分遮罩</h1><p>涂抹上衣源图中的翼片投影，检查服装保留区。黄色框只是重叠提示，默认没有移除区域。
红色＝待移除，绿色＝明确保留，擦除＝恢复未标注。右侧仅为静态预览，不是采用或正式导出。</p>
<div class="toolbar"><label>笔刷 <select id="mode"><option value="remove">待移除</option><option value="keep">明确保留</option><option value="erase">擦除标注</option></select></label>
<label>半径 <input id="radius" type="range" min="1" max="64" value="12"></label><label>缩放 <input id="zoom" type="range" min="25" max="150" value="50"></label>
<button id="undo">撤销</button><button id="redo">重做</button><button id="clear">重置画布</button><button id="save">保存完整草稿</button>
<label>恢复草稿 <input id="load" type="file" accept=".json"></label><label><input id="hints" type="checkbox" checked>重叠提示</label><label><input id="reference" type="checkbox" checked>右侧叠加翼片参考</label>
<p id="status" role="status">加载图像…</p></div><main><section><h2>原始上衣与标注</h2><div class="viewport"><canvas id="edit" aria-label="上衣遮罩编辑画布"></canvas></div></section>
<section><h2>仅按当前遮罩隐藏后的预览</h2><div class="viewport"><canvas id="preview" aria-label="拆分预览"></canvas></div></section></main>
<p>最多 500 笔、4096 个路径点。保存前检查衣领、肩部与蝴蝶结。未标注区域保留，原图不改写；保存后将 JSON 发回以校验和生成候选。</p>
<script id="state" type="application/json">{payload}</script><script>{SCRIPT}</script></html>'''
