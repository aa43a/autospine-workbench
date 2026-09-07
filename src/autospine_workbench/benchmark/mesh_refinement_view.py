"""Before/after wireframe bends alongside source-bound numerical QA."""
from html import escape
from .mesh_candidate_view import render_mesh_candidate
from ..asset.joints.mesh_weights import _deform,_frames


def render_refinement(candidate,baseline,report,skeleton,composite,images):
    page=render_mesh_candidate(candidate,report,composite,images)
    bones={b['id']:b for b in skeleton['bones']};layers={l['layer_id']:l for l in candidate['layers']};cards=[]
    for old,new in zip(baseline['layers'],report['layers']):
        if not new['weights']:continue
        chain=[bones[i['bone_id']] for i in new['weights'][0]]
        before=_deform(old['weights'],_frames(chain,90));after=_deform(new['weights'],_frames(chain,90))
        allpoints=before+after
        left=min(p[0] for p in allpoints)-10;top=min(p[1] for p in allpoints)-10
        width=max(p[0] for p in allpoints)-left+10;height=max(p[1] for p in allpoints)-top+10
        diagrams=[]
        for label,points,color in (('原距离权重',before,'#ab3434'),('关节平面权重',after,'#00776a')):
            polygons=[]
            for tri in new['triangles']:
                coords=' '.join(f'{points[i][0]},{points[i][1]}' for i in tri)
                polygons.append(f'<polygon points="{coords}" fill="none" stroke="{color}" stroke-width=".4"/>')
            diagrams.append(f'<div><p>{label}</p><svg style="max-height:360px" viewBox="{left} {top} {width} {height}">{"".join(polygons)}</svg></div>')
        cards.append(f'<article><h2>{escape(layers[new["layer_id"]]["name"])}</h2><div style="display:grid;grid-template-columns:1fr 1fr">{"".join(diagrams)}</div></article>')
    section='<h2 id="bends">+90° 网格形状对照</h2><p>仅比较变形后的网格线，未做纹理渲染或Runtime捕获。</p><main>'+''.join(cards)+'</main>'
    return page.replace('</html>',section+'</html>')
