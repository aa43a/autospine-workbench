"""Bind proxy depth locations to existing official same-frame screenshots."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes


def map_pixels(locations,info,size):
    left=info['left'];top=info['bottom']+info['height']
    if (any(type(v) is not int for v in (left,top,info['width'],info['height']))
            or tuple(size)!=(info['width'],info['height'])):
        raise ValueError('runtime_depth_review_native_grid_required')
    if any(len(p)!=2 or any(type(v) is not int for v in p) for p in locations):
        raise ValueError('runtime_depth_review_pixel_coordinates')
    points=[(x-left,y+top) for x,y in locations]
    if any(not 0<=x<size[0] or not 0<=y<size[1] for x,y in points):
        raise ValueError('runtime_depth_review_pixel_bounds')
    return points


def run(diagnostic,capture,output):
    if output.exists():raise ValueError('output_exists')
    raw=diagnostic.read_bytes();report=json.loads(raw)
    runtime_raw=(capture/'partitioned/report.json').read_bytes();runtime=json.loads(runtime_raw)
    files=AnimatedStore(capture/'isolated-store').read(runtime['bundle_sha256'])
    if (runtime.get('passed') is not True or sha256(files['skeleton.json']).hexdigest()!=report['skeleton_sha256']
            or report.get('pixel_locations') is not True):raise ValueError('runtime_depth_review_identity')
    info=runtime['info']
    frames={(r['animation'],r['time']):r for r in runtime['results']}
    shots={(s['animation'],s['index']):s for s in runtime['screenshots']}
    selected=[r for r in report['rows'] if r['hypotheses'][-1]['status']=='requires_partition_or_more_depth']
    if not selected or len(selected)>32:raise ValueError('runtime_depth_review_frame_limit')
    output.mkdir(parents=True,exist_ok=False);cards=[];records=[]
    for index,row in enumerate(selected):
        h=row['hypotheses'][-1]
        if h['time']!=row['time'] or h['pair']!=[row['region'],row['body']]:raise ValueError('runtime_depth_review_sample_identity')
        frame=frames['external-motion',row['time']];shot=shots['external-motion',frame['index']]
        name=shot['file']
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('runtime_depth_review_image_path')
        image_raw=(capture/'partitioned'/name).read_bytes()
        if sha256(image_raw).hexdigest()!=shot['sha256']:raise ValueError('runtime_depth_review_image_identity')
        image=Image.open(BytesIO(image_raw)).convert('RGBA')
        if image.size!=(info['width'],info['height']):raise ValueError('runtime_depth_review_image_size')
        markers={k:map_pixels(values,info,image.size) for k,values in h['pixel_locations'].items()}
        for k,values in markers.items():
            if len(values)!=h['counts'][k] or len(set(values))!=len(values):raise ValueError('runtime_depth_review_pixel_inventory')
        points=[p for values in markers.values() for p in values]
        if not points or any(not 0<=x<image.width or not 0<=y<image.height for x,y in points):
            raise ValueError('runtime_depth_review_pixel_bounds')
        box=(max(0,min(x for x,y in points)-24),max(0,min(y for x,y in points)-24),
             min(image.width,max(x for x,y in points)+25),min(image.height,max(y for x,y in points)+25))
        crop=image.crop(box);crop.save(output/f'{index}-runtime.png')
        overlay=Image.new('RGBA',crop.size)
        for kind,color in [('back',(70,180,255,210)),('ambiguous',(255,170,0,190))]:
            for x,y in markers[kind]:overlay.putpixel((x-box[0],y-box[1]),color)
        overlay.save(output/f'{index}-markers.png');(output/f'{index}-full.png').write_bytes(image_raw)
        colors=[image.getpixel(p) for p in points]
        records.append(dict(time=row['time'],region=row['region'],body=row['body'],
            screenshot_sha256=shot['sha256'],frame_index=frame['index'],crop=list(box),
            marker_counts={k:len(v) for k,v in markers.items()},
            framebuffer_alpha_min=min(v[3] for v in colors),framebuffer_alpha_max=max(v[3] for v in colors)))
        cards.append(f'<section><h2>{row["time"]:g} 秒</h2><p>不确定 {len(markers["ambiguous"])} · 代理深度在后 {len(markers["back"])}</p>'
            f'<div class="crop"><img src="{index}-runtime.png"><img class="markers" src="{index}-markers.png"></div>'
            f'<p><a href="{index}-full.png">查看同帧完整截图</a></p></section>')
    receipt=dict(source_artifact_sha256=report['source_artifact_sha256'],skeleton_sha256=report['skeleton_sha256'],
        diagnostic_sha256=sha256(raw).hexdigest(),runtime_report_sha256=sha256(runtime_raw).hexdigest(),
        capture_bundle_sha256=runtime['bundle_sha256'],runtime_version=runtime['runtime_version'],frames=records,
        authority='none',selected=False,runtime_recaptured=False,
        scope='same_frame_proxy_marker_alignment_not_gpu_material_ownership_or_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>拳击近接触对照</title>'
        '<style>body{background:#15212b;color:#edf2f7;font:16px system-ui;padding:24px}main{display:flex;flex-wrap:wrap;gap:24px}'
        'section{background:#263744;padding:16px;border-radius:8px}.crop{position:relative;line-height:0;background:repeating-conic-gradient(#536271 0 25%,#687783 0 50%) 0/16px 16px}'
        '.crop img{width:320px;image-rendering:pixelated}.markers{position:absolute;inset:0}.hide .markers{display:none}a{color:#7cceff}</style>'
        '<h1>拳击近接触：同帧 Runtime 对照</h1><p>橙色：模型不确定；蓝色：代理深度在裙片后方。标记不是可见错误裁定。</p>'
        '<p>现有官方截图，未重新捕获。保留原候选顺序；透明度只说明合成结果，不证明部件归属正确。</p>'
        '<label><input type="checkbox" checked onchange="document.body.classList.toggle(\'hide\',!this.checked)">显示深度标记</label>'
        '<main>'+''.join(cards)+'</main>',encoding='utf-8')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('diagnostic','capture','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.diagnostic,a.capture,a.output)
