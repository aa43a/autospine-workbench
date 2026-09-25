"""Join tracked material to exact-time, hash-verified existing Runtime captures."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from PIL import Image


def screen_pixel(world, info):
    x=math.floor(world[0]-info['left'])
    y=info['height']-1-math.floor(world[1]-info['bottom'])
    return (x,y) if 0<=x<info['width'] and 0<=y<info['height'] else None


def run(trace_path, runtime, output):
    trace=json.loads(trace_path.read_bytes())
    report_raw=(runtime/'report.json').read_bytes(); report=json.loads(report_raw)
    if report['bundle_sha256']!=trace['artifact_sha256']:
        raise ValueError('overlap_runtime_identity_mismatch')
    if report['profile']!='official-webgl-swiftshader-native-v1':
        raise ValueError('overlap_runtime_camera_profile_unsupported')
    results={(r['animation'],r['index']):r for r in report['results']}
    screenshots={results[(s['animation'],s['index'])]['time']:s
                 for s in report['screenshots'] if s['animation']=='external-motion'}
    frames=[]; missing=[]
    for frame in trace['frames']:
        if frame['time'] not in screenshots:
            missing.append(frame['time']);continue
        shot=screenshots[frame['time']]; location=(runtime/shot['file']).resolve()
        if not location.is_relative_to(runtime.resolve()):raise ValueError('overlap_capture_path')
        raw=location.read_bytes()
        if sha256(raw).hexdigest()!=shot['sha256']:raise ValueError('overlap_capture_changed')
        image=Image.open(BytesIO(raw)).convert('RGBA'); info=report['info']
        if image.size!=(info['width'],info['height']):raise ValueError('overlap_capture_size')
        records=[]
        for row in frame['records']:
            if row['reference_alpha']!=0:continue
            pixel=screen_pixel(row['world'],info)
            if pixel is None:raise ValueError('overlap_material_outside_capture')
            alpha=image.getpixel(pixel)[3]
            records.append(dict(source_texel=row['source_texel'],world=row['world'],
                                pixel=list(pixel),framebuffer_alpha=alpha))
        frames.append(dict(time=frame['time'],file=shot['file'],sha256=shot['sha256'],
            exposed_source_texels=len(records),unique_screen_pixels=len({tuple(r['pixel']) for r in records}),
            framebuffer_below_8=sum(r['framebuffer_alpha']<8 for r in records),
            alpha_min=min((r['framebuffer_alpha'] for r in records),default=None),records=records))
    result=dict(artifact_sha256=trace['artifact_sha256'],runtime_version=report['runtime_version'],
        capture_report_sha256=sha256(report_raw).hexdigest(),trace_sha256=sha256(trace_path.read_bytes()).hexdigest(),
        frames=frames,unmatched_times=missing,capture_reused=True,selected=False,authority='none',
        scope='exposed_material_pixel_alpha_not_adjacent_gap_color_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({**result,'frames':[{k:v for k,v in r.items() if k!='records'} for r in frames]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('trace','runtime','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.trace,args.runtime,args.output)
