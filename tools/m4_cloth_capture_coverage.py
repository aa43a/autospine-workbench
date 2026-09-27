"""Match cloth failures to exact-time saved framebuffer images without resampling."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import html
from PIL import Image
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_motion_contact import transport


def run(experiment,grid_path,runtime,output):
    output.mkdir(parents=True,exist_ok=False)
    diagnosis=json.loads((experiment/'report.json').read_bytes())
    raw=(experiment/'skeleton.json').read_bytes();doc=json.loads(raw)
    manifest=json.loads((runtime/'report.json').read_bytes());grid=json.loads(grid_path.read_bytes())
    if (manifest['status']!='complete' or manifest['skeleton_sha256']!=sha256(raw).hexdigest() or
        diagnosis['skeleton_sha256']!=manifest['skeleton_sha256'] or
        diagnosis['source_candidate']!=grid['candidate_bundle_sha256']):
        raise ValueError('cloth_capture_identity')
    screenshots={}
    for row in manifest['rows']:
        folder=runtime/row['folder']/'runtime';captured=json.loads((folder/'report.json').read_bytes())
        if captured!=row['runtime']:raise ValueError('cloth_capture_report_changed')
        for shot in captured['screenshots']:
            if shot['animation']!='external-motion':continue
            frame=captured['results'][shot['index']]
            if frame['index']!=shot['index'] or frame['animation']!=shot['animation']:
                raise ValueError('cloth_capture_frame_index')
            screenshots.setdefault(frame['time'],(folder,shot,captured['info']))
    records=[];missing=[];cards=[]
    for frame in diagnosis['frames']:
        if not frame['uncovered']:continue
        time=frame['time']
        if time not in screenshots:missing.append(time);continue
        folder,shot,info=screenshots[time];path=(folder/shot['file']).resolve()
        if not path.is_relative_to(folder.resolve()):raise ValueError('cloth_capture_path')
        image_raw=path.read_bytes()
        if sha256(image_raw).hexdigest()!=shot['sha256']:raise ValueError('cloth_capture_image_changed')
        image=Image.open(BytesIO(image_raw)).convert('RGBA')
        if image.size!=(info['width'],info['height']):raise ValueError('cloth_capture_viewport')
        posed=sample(doc,'external-motion',time)[0];points=[]
        for failure in frame['uncovered']:
            i=failure['sample'];world=transport(posed[grid['limb']],grid['grid'][i]['anchor'])
            x=math.floor(world[0]-info['left']);y=info['height']-1-math.floor(world[1]-info['bottom'])
            if not 0<=x<image.width or not 0<=y<image.height:raise ValueError('cloth_capture_outside_frame')
            pixel=image.getpixel((x,y))
            points.append(dict(sample=i,world=world,pixel=[x,y],cpu_cloth_alpha=failure['alpha'],
                framebuffer_rgba=list(pixel),transparent_pixel=pixel[3]<8))
        records.append(dict(time=time,folder=str(folder),file=shot['file'],index=shot['index'],
            screenshot_sha256=shot['sha256'],points=points))
        x,y=points[0]['pixel'];src=html.escape(os.path.relpath(path,output).replace('\\','/'),quote=True)
        markers=''.join(f'<i style="left:{158+4*(p["pixel"][0]-x)}px;top:{158+4*(p["pixel"][1]-y)}px"></i>' for p in points)
        cards.append(f'<article><h2>{time:.9f} 秒</h2><div class="crop"><img src="{src}" style="width:{4*image.width}px;left:{160-4*x}px;top:{160-4*y}px">{markers}</div>'
            f'<p>{len(points)} 个材质覆盖告警，{sum(p["transparent_pixel"] for p in points)} 个对应屏幕像素透明度低于 8。</p>'
            f'<a href="{src}">完整原始捕获图</a></article>')
    summary=dict(failed_times=sum(bool(f['uncovered']) for f in diagnosis['frames']),matched_times=len(records),
        missing_exact_screenshots=len(missing),matched_points=sum(len(r['points']) for r in records),
        transparent_points=sum(p['transparent_pixel'] for r in records for p in r['points']))
    result=dict(summary=summary,frames=records,missing_exact_times=missing,skeleton_sha256=manifest['skeleton_sha256'],
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (grid_path,experiment/'report.json',runtime/'report.json')},
        authority='none',selected=False,scope='exact_capture_pixel_alpha_not_garment_ownership_or_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(result))
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>裙片覆盖 · 同帧捕获</title>
<style>body{background:#16212b;color:#e8f0fa;font:16px system-ui;padding:20px}main{display:flex;flex-wrap:wrap;gap:20px}article{width:350px}.crop{position:relative;width:320px;height:320px;overflow:hidden;background:#bbb}img{position:absolute;max-width:none;image-rendering:pixelated}i{position:absolute;width:6px;height:6px;border:1px solid red;border-radius:50%}a{color:#6dd6ff}</style>
<h1>裙片覆盖 · 同帧捕获</h1><p>红圈定位告警采样点；放大图来自未修改的官方 Runtime 捕获。屏幕不透明也可能是腿部显露，不能等同于衣服覆盖正确。</p>'''
    page+=f'<p>匹配 {len(records)} / {summary["failed_times"]} 个失败时刻；其余 {len(missing)} 个没有同一时刻截图，保持未验证。候选未采用。</p><main>'+''.join(cards)+'</main></html>'
    (output/'index.html').write_text(page,encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('experiment','grid_path','runtime','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.experiment,a.grid_path,a.runtime,a.output)
