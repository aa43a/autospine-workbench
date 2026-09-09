"""Static topology and selectable CPU bend probes, not runtime rendering."""
from html import escape
import json
from ..joints.mesh_weights import _rotate, _deform
from .component_weight_review import LABELS


def _poses(mesh, skeleton):
    bones = {b['id']: b for b in skeleton['bones']}
    chain = [bones[b] for b in mesh['bone_ids']]
    result = []
    for probe in mesh['qa']['probes']:
        name, angle = probe['id'].rsplit('_', 1)
        index = mesh['bone_ids'].index(name); pivot = chain[index]['head_xy']
        frames = {}
        for i, bone in enumerate(chain):
            head, rotation = bone['head_xy'], bone['world_rotation_degrees']
            if i >= index:
                delta = _rotate([head[k]-pivot[k] for k in (0,1)], float(angle))
                head = [pivot[k]+delta[k] for k in (0,1)]; rotation += float(angle)
            frames[bone['id']] = head, rotation
        moved = _deform(mesh['weights'], frames)
        result.append(dict(id=probe['id'], points=moved, qa=probe))
    return result


def render(document, skeleton, pose_overrides=None):
    sections, payload = [], []
    for row in document['records']:
        mesh = row['mesh']; number = len(payload)
        reason = '；'.join(LABELS.get(r, r) for r in row['reason_codes'])
        if not mesh or not mesh['qa']:
            sections.append(f'<section><h2>{escape(row["layer_id"])} / {escape(row["component_id"])}</h2>'
                            f'<p>{escape(reason)}</p></section>')
            continue
        poses = _poses(mesh, skeleton)
        if pose_overrides and (row['layer_id'],row['component_id']) in pose_overrides:
            corrected = pose_overrides[row['layer_id'],row['component_id']]
            poses = [dict(id='原 '+p['id'],points=p['points'],qa=p['qa']) for p in poses] + corrected
        points = [p for pose in poses for p in pose['points']]
        x, y = min(p[0] for p in points)-10, min(p[1] for p in points)-10
        w, h = max(p[0] for p in points)-x+10, max(p[1] for p in points)-y+10
        payload.append(dict(poses=poses, triangles=mesh['triangles'], setup=mesh['vertices_xy']))
        options = ''.join(f'<option value="{i}" {"selected" if i == 4 else ""}>{escape(p["id"])}</option>' for i,p in enumerate(poses))
        sections.append(f'<section data-mesh="{number}"><h2>{escape(row["layer_id"])} / {escape(row["component_id"])}</h2>'
                        f'<p>{len(mesh["vertices_xy"])} 顶点 · {len(mesh["triangles"])} 三角形 · '
                        f'{"数值门槛通过" if mesh["qa"]["passed"] else "变形检查阻塞"}</p>'
                        f'<select aria-label="检查姿态">{options}</select><p class="qa"></p>'
                        f'<svg viewBox="{x} {y} {w} {h}"></svg><p>{escape(reason)}</p></section>')
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False).replace('<','\\u003c')
    script = '''const data=PAYLOAD;
const area=(points,t)=>{const [a,b,c]=t.map(i=>points[i]);return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);};
document.querySelectorAll('[data-mesh]').forEach(section=>{
 const model=data[Number(section.dataset.mesh)], select=section.querySelector('select');
 const draw=()=>{const pose=model.poses[Number(select.value)], svg=section.querySelector('svg');
 svg.replaceChildren(); model.triangles.forEach(t=>{const p=document.createElementNS('http://www.w3.org/2000/svg','polygon');
 p.setAttribute('points',t.map(i=>pose.points[i].join(',')).join(' '));
 const ratio=area(pose.points,t)/area(model.setup,t);
 if(ratio<=0)p.style.fill='#ff405acc';else if(ratio<.5||ratio>2)p.style.fill='#ffbd4588';
 svg.append(p);});
 section.querySelector('.qa').textContent=`翻转 ${pose.qa.inversions} · 面积比 ${pose.qa.min_area_ratio.toFixed(3)}—${pose.qa.max_area_ratio.toFixed(3)} · 最大边长倍率 ${pose.qa.max_edge_stretch.toFixed(3)}`;};
 select.addEventListener('change',draw);draw();});'''.replace('PAYLOAD', data)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>区域 Mesh 检查</title>
<style>body{{background:#111a24;color:#edf3fa;font:16px system-ui;margin:24px}}a{{color:#8bdcff}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}}section{{background:#223040;padding:16px}}
svg{{width:100%;height:430px;background:#17212d}}polygon{{fill:#51b8d733;stroke:#8cdbed;stroke-width:.65}}select{{padding:8px}}</style>
<h1>{escape(document['project_id'])} · 区域三角网格与弯曲检查</h1>
<p>选择姿态查看 CPU 网格变形。采用独立 alpha 掩膜诊断与关节平面权重；源 PNG、归属记录不变。</p>
<p>红色标出翻转三角形，黄色标出面积压缩或拉伸超限。</p>
<p>这不是 Spine 播放验收。原纹理共享下的跨区泄漏、附件接缝和 Runtime 尚未验证。</p>
<a href="index.html">归属复核</a> · <a href="weights.html">采样权重</a>
<main>{''.join(sections)}</main><script>{script}</script></html>'''
