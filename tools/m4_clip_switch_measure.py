"""Measure captured topology switches; ignore invisible RGB in transparent pixels."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image


def image(folder,record):
    name=record['name']
    if Path(name).name!=name:raise ValueError('capture_filename')
    raw=(folder/name).read_bytes()
    if sha256(raw).hexdigest()!=record['sha256']:raise ValueError('capture_image_identity')
    rgba=np.asarray(Image.open(BytesIO(raw)).convert('RGBA'),dtype=float)
    if rgba.shape[:2]!=(record['height'],record['width']):raise ValueError('capture_dimensions')
    return rgba


def measure(a,b):
    if a.shape!=b.shape:raise ValueError('capture_camera_changed')
    def visible(rgba):return np.concatenate((rgba[:,:,:3]*rgba[:,:,3:]/255,rgba[:,:,3:]),axis=2)
    diff=np.abs(visible(a)-visible(b));maximum=diff.max(axis=2)
    return dict(changed_over_one=int((maximum>1).sum()),changed_over_eight=int((maximum>8).sum()),
                maximum_visible_channel_delta=float(maximum.max()),maximum_alpha_delta=float(diff[:,:,3].max()))


def run(folder):
    raw=(folder/'capture.json').read_bytes();capture=json.loads(raw)
    samples={(r['segment'],r['label']):r for r in capture['samples']};records=[]
    for (index,label),before in samples.items():
        if label!='prior':continue
        after=samples[index,'switch'];sides=[]
        for side in (0,1):sides.append(measure(image(folder,before['files'][side]),image(folder,after['files'][side])))
        records.append(dict(segment=index,time=after['time'],baseline=sides[0],candidate=sides[1]))
    return dict(authority='none',scope='native_framebuffer_discrete_switch_not_full_animation_acceptance',
                capture_sha256=sha256(raw).hexdigest(),artifacts=capture['artifacts'],records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);a=p.parse_args()
    result=run(a.folder)
    (a.folder/'visible-measurements.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(sorted(result['records'],key=lambda r:r['candidate']['changed_over_eight'],reverse=True)[:5]))
