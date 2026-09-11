"""Synchronized uncorrected/corrected discrete views with explicit evidence limits."""
from html import escape
import json
import math
from .ordinary_sleeve_deform_validation import validate
from .ordinary_sleeve import angles
from .ordinary_sleeve_review import STYLE, SCRIPT
from .sleeve_helpers import frames
from .component_temporal_qa import passed
from ..joints.mesh_weights import _deform, _rotate


def render(document, *, repair, source, draft, skeleton):
    validate(document, repair=repair, source=source, draft=draft, skeleton=skeleton)
    bones = {b['id']: b for b in skeleton['bones']}
    cards, payload = [], []
    for row in document['records']:
        for corrected, title in [(False, '修正前'), (True, '离散修正候选')]:
            tracks = []
            if row['tracks']:
                chain = [bones[b] for b in row['bone_ids']]
                for track in row['tracks']:
                    samples = []
                    for tick in range(0, 129, 4):
                        values = angles(track['amplitudes'], tick)
                        transforms = frames(chain, dict(zip(track['drivers'], values)))
                        points = _deform(row['weights'], transforms)
                        if corrected:
                            for delta in track['keys'][tick]['offsets']:
                                v = delta['vertex_id']
                                points[v] = [points[v][i]+delta['delta_xy'][i] for i in (0, 1)]
                        pose_bones = []
                        for bone in chain:
                            head, rotation = transforms[bone['id']]
                            offset = _rotate([math.dist(bone['head_xy'], bone['tail_xy']), 0], rotation)
                            pose_bones.append(dict(id=bone['id'], head_xy=head,
                                                  tail_xy=[head[i]+offset[i] for i in (0, 1)]))
                        samples.append(dict(tick=tick, points=points, angles=values, bones=pose_bones))
                    qa = track['qa'] if corrected else track['before_qa']
                    tracks.append(dict(bone_id=track['bone_id'], qa=qa, samples=samples,
                                       failed_ticks=sum(not passed(q) for q in qa)))
            index = len(payload)
            payload.append(dict(available=bool(tracks), triangles=row.get('triangles', []), tracks=tracks))
            name = escape(f"{row['layer_id']} / {row['component_id']} · {title}")
            status = '离散姿态仍有失败或来源未就绪' if row['status'] == 'blocked' else '离散采样通过，连续时间与 Runtime 未验证'
            diagnostics = ''.join(f'<p>{escape(t["bone_id"])}：相邻修正增量 {t["max_adjacent_delta_px"]:.4f}px；'
                                  f'二阶差分 {t["max_second_difference_px"]:.4f}px</p>' for t in row['tracks']) if corrected else ''
            cards.append(f'<section class="card" data-row="{index}"><h2>{name}</h2><p>{status}</p>'
                         f'<p>{escape("；".join(row["reason_codes"]))}</p>{diagnostics}'
                         + ('<label>测试轨道 <select aria-label="测试轨道"></select></label>'
                            '<p class="qa"></p><svg role="img" aria-label="普通袖修正对比"></svg>'
                            if tracks else '<p>无可用轨道，保留阻塞区域。</p>') + '</section>')
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    sync = """
// Both sides of each comparison use exactly the same canvas scale and origin.
for(let i=0;i<views.length;i+=2){
  const a=views[i],b=views[i+1];if(!b)continue;
  a.boxes=a.boxes.map((box,j)=>{
    const x=box.split(' ').map(Number),y=b.boxes[j].split(' ').map(Number);
    const left=Math.min(x[0],y[0]),top=Math.min(x[1],y[1]);
    return `${left} ${top} ${Math.max(x[0]+x[2],y[0]+y[2])-left} ${Math.max(x[1]+x[3],y[1]+y[3])-top}`;
  });b.boxes=a.boxes;
}
document.querySelectorAll('.card select').forEach(s=>s.addEventListener('change',()=>{
  document.querySelectorAll('.card select').forEach(o=>o.value=s.value);draw();
}));draw();
"""
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>普通袖离散修正对比</title><style>' + STYLE
            + 'main{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:700px){main{grid-template-columns:1fr}}</style>'
            '<header><h1>普通袖离散修正对比</h1><p>129 tick 检查，时间轴展示33个采样姿态。只显示几何，不绘制纹理。</p>'
            '<p>修正增量和二阶差分是诊断值，不是连续性通过证明；尚未验证目标插值、接缝或官方Runtime。</p>'
            f'<details><summary>修正来源</summary><p>{escape(document["profile"])}</p><p>{escape(document["repair_sha256"])}</p></details>'
            '<div class="controls"><button id="play">播放</button><button id="setup">初始姿态</button>'
            '<label>时间轴 <input id="time" type="range" min="0" max="32" value="0" step="1"></label><output id="clock"></output></div></header>'
            f'<main>{"".join(cards)}</main><script type="application/json" id="data">{encoded}</script>'
            f'<script>{SCRIPT}{sync}</script></html>')
