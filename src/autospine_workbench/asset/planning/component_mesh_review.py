"""Scrubbable CPU diagnostic tracks, not runtime rendering."""
from html import escape
import json
from pathlib import Path
from .component_mesh_tracks import _poses, tracks
from .component_weight_review import LABELS



def render(document, skeleton, pose_overrides=None, fk=False):
    sections, payload = [], []
    for row in document['records']:
        mesh = row['mesh']; number = len(payload)
        reason = '；'.join(LABELS.get(r, r) for r in row['reason_codes'])
        if not mesh or not mesh['qa']:
            sections.append(f'<section><h2>{escape(row["layer_id"])} / {escape(row["component_id"])}</h2>'
                            f'<p>{escape(reason)}</p></section>')
            continue
        corrected = (pose_overrides or {}).get((row['layer_id'],row['component_id']))
        animation = tracks(mesh, skeleton, corrected)
        points = [p for track in animation for mode in ('original','corrected') for frame in track[mode] for p in frame]
        x, y = min(p[0] for p in points)-10, min(p[1] for p in points)-10
        w, h = max(p[0] for p in points)-x+10, max(p[1] for p in points)-y+10
        payload.append(dict(tracks=animation, triangles=mesh['triangles'], setup=mesh['vertices_xy']))
        if fk:
            bones={b['id']:b for b in skeleton['bones']}
            payload[-1].update(bones=[bones[b] for b in mesh['bone_ids']],weights=mesh['weights'])
        options = ''.join(f'<option value="{i}" {"selected" if i == min(1,len(animation)-1) else ""}>{escape(t["bone_id"])}</option>' for i,t in enumerate(animation))
        comparison = '<label>对照 <select data-variant><option value="original">原结果</option><option value="corrected" selected>局部修正</option></select></label>' if corrected else ''
        sections.append(f'<section data-mesh="{number}"><h2>{escape(row["layer_id"])} / {escape(row["component_id"])}</h2>'
                        f'<p>{len(mesh["vertices_xy"])} 顶点 · {len(mesh["triangles"])} 三角形 · '
                        f'{"数值门槛通过" if mesh["qa"]["passed"] else "变形检查阻塞"}</p>'
                        f'<label>关节 <select data-joint aria-label="检查关节">{options}</select></label>{comparison}<p class="qa"></p>'
                        f'<svg viewBox="{x} {y} {w} {h}"></svg><p>{escape(reason)}</p></section>')
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False).replace('<','\\u003c')
    code = (Path(__file__).resolve().parents[4] / 'web/modules/component-mesh-timeline.js').read_text('utf-8')
    script = code.replace('export function ', 'function ') + '\nmountMeshTimeline(document,' + data + ');'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>区域 Mesh 检查</title>
<style>body{{background:#111a24;color:#edf3fa;font:16px system-ui;margin:24px}}a{{color:#8bdcff}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}}section{{background:#223040;padding:16px}}
svg{{width:100%;height:430px;background:#17212d}}polygon{{fill:#51b8d733;stroke:#8cdbed;stroke-width:.65}}select,button{{padding:8px}}.mesh-timeline{{position:sticky;top:0;z-index:5;border:1px solid #568}}input[type=range]{{width:min(60vw,800px);vertical-align:middle}}</style>
<h1>{escape(document['project_id'])} · 区域三角网格与弯曲检查</h1>
<p>拖动时间轴或点击播放查看 CPU 网格变形。采用独立 alpha 掩膜诊断与关节平面权重；源 PNG、归属记录不变。</p>
<p>红色标出翻转三角形，黄色标出面积压缩或拉伸超限。</p>
<p>这不是 Spine 播放验收。原纹理共享下的跨区泄漏、附件接缝和 Runtime 尚未验证。</p>
<a href="index.html">归属复核</a> · <a href="weights.html">采样权重</a>
<main>{''.join(sections)}</main><script>{script}</script></html>'''
