"""Exact-candidate UV localization and same-frame alpha support for mixed triangles."""
import argparse
from hashlib import sha256
from html import escape
from io import BytesIO
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.depth_triangle_summary import summarize
from autospine_workbench.targets.spine43.seam_raster import mask, texture


def build(folder, trace, output):
    import numpy as np
    from PIL import Image, ImageDraw
    raw = trace.read_bytes(); evidence = json.loads(raw)
    receipt = json.loads((folder/'report.json').read_bytes())
    artifact = receipt['candidate_bundle_sha256']
    if evidence['artifact_sha256'] != artifact:
        raise ValueError('triangle_review_candidate_mismatch')
    summary = summarize(evidence['records'])
    files = AnimatedStore(folder/'isolated-store').read(artifact)
    doc = json.loads(files['skeleton.json'])
    slots = {s['name']: s for s in doc['slots']}
    def attachment(slot):
        return doc['skins'][0]['attachments'][slot][slots[slot]['attachment']]
    def png(slot):
        return files['images/'+attachment(slot).get('path', slots[slot]['attachment'])+'.png']
    tasks = [(p['pair'], t) for p in summary['pairs'] for t in p['triangles']
             if t['status'] == 'within_frame_mixed']
    if len(tasks) > 64:
        raise ValueError('triangle_review_card_limit')
    output.mkdir(parents=True, exist_ok=False)
    cards = []; rows = []
    for number, (pair, triangle) in enumerate(tasks):
        arm, body = pair; index = triangle['triangle']; time = triangle['mixed_times'][0]
        mesh = attachment(arm); indices = mesh['triangles'][index*3:index*3+3]
        if len(indices) != 3: raise ValueError('triangle_review_index_invalid')
        image = Image.open(BytesIO(png(arm))).convert('RGBA')
        uv = [(mesh['uvs'][i*2]*image.width, mesh['uvs'][i*2+1]*image.height) for i in indices]
        left = max(0, math.floor(min(p[0] for p in uv))-35)
        top = max(0, math.floor(min(p[1] for p in uv))-35)
        right = min(image.width, math.ceil(max(p[0] for p in uv))+35)
        bottom = min(image.height, math.ceil(max(p[1] for p in uv))+35)
        crop = image.crop((left, top, right, bottom))
        ImageDraw.Draw(crop).polygon([(x-left,y-top) for x,y in uv], outline='#ffb52e', width=2)
        crop.save(output/f'{number}-uv.png')
        points = sample(doc, 'external-motion', time)[0]
        world = [(points[arm][i][0], -points[arm][i][1]) for i in indices]
        x = math.floor(min(p[0] for p in world))-35; y = math.floor(min(p[1] for p in world))-35
        rect = [x,y,math.ceil(max(p[0] for p in world))+35-x,math.ceil(max(p[1] for p in world))+35-y]
        if rect[2]*rect[3] > 262144: raise ValueError('triangle_review_roi_limit')
        a,b = [mask(attachment(s),points[s],texture(png(s)),rect)>=8 for s in pair]
        rgb = np.full((rect[3],rect[2],3),35,dtype=np.uint8)
        rgb[a]=[75,155,235]; rgb[b]=[102,190,140]; rgb[a&b]=[163,108,208]
        frame = Image.fromarray(rgb)
        ImageDraw.Draw(frame).polygon([(px-x,py-y) for px,py in world],outline='#ffb52e',width=2)
        frame.save(output/f'{number}-frame.png')
        row = dict(pair=pair,triangle=index,time=time,uv_crop=[left,top,right,bottom],world_roi=rect,
                   mixed_times=triangle['mixed_times'])
        rows.append(row)
        player=(folder/'runtime/player.html').resolve().as_uri()+f'?time={time}'
        cards.append(f'<section><h2>{escape(arm)} / {escape(body)} · 三角形 {index}</h2>'
            f'<p>首次同帧混合 {time:.6f}s · 共 {len(triangle["mixed_times"])} 个源帧 '
            f'<a href="{escape(player,quote=True)}">打开该帧播放器</a></p>'
            f'<figure><img src="{number}-uv.png"><figcaption>源纹理 UV 定位</figcaption></figure>'
            f'<figure><img src="{number}-frame.png"><figcaption>同帧 alpha 覆盖：蓝=手臂，绿=躯干，紫=重叠</figcaption></figure></section>')
    report=dict(artifact_sha256=artifact,trace_sha256=sha256(raw).hexdigest(),rows=rows,
                authority='none',selected=False,scope='first_mixed_source_frame_per_triangle_cpu_alpha_not_runtime_depth')
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>局部遮挡定位</title>'
        '<style>body{background:#14222e;color:#eee;font:16px sans-serif;margin:28px}section{border-top:1px solid #567;padding:16px}figure{display:inline-block;vertical-align:top;margin:12px}img{min-width:200px;max-width:450px;image-rendering:pixelated;background:#344450}a{color:#8ddfff}</style>'
        '<h1>局部遮挡定位</h1><p>橙线为同一个三角形。左侧按原始 UV 定位，右侧使用对应时间的实际变形顶点；二者不是同一坐标系。</p>'
        '<p>紫色仅说明两层 alpha 重叠，不表示已确认前后归属。代理深度存在不确定性；本页不修改绘制顺序，不代表 Runtime 视觉验收。</p>'
        +''.join(cards),encoding='utf-8')
    print(json.dumps(dict(artifact=artifact,cards=len(rows),output=str(output))))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('folder','trace','output'): parser.add_argument(name,type=Path)
    args=parser.parse_args();build(args.folder,args.trace,args.output)
