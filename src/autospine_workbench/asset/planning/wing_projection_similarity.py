"""Observed coincident pixels are not proof of anatomical occlusion."""
from io import BytesIO
import numpy as np
from PIL import Image
from .mount_contact import mask


def compare(source,source_raw,target,target_raw):
    mask(source,source_raw);mask(target,target_raw)
    sx,sy,sr,sb=source['bbox'];tx,ty,tr,tb=target['bbox']
    x,y,r,b=max(sx,tx),max(sy,ty),min(sr,tr),min(sb,tb)
    if r<=x or b<=y:return {'overlap_pixels':0,'rgb_exact_pixels':0,'rgba_exact_pixels':0,'rgb_mae':None,'alpha_mae':None}
    with Image.open(BytesIO(source_raw)) as image:
        a=np.asarray(image.convert('RGBA').crop((x-sx,y-sy,r-sx,b-sy)),dtype=np.int16)
    with Image.open(BytesIO(target_raw)) as image:
        c=np.asarray(image.convert('RGBA').crop((x-tx,y-ty,r-tx,b-ty)),dtype=np.int16)
    overlap=(a[:,:,3]>=8)&(c[:,:,3]>=8);a=a[overlap];c=c[overlap]
    return {'overlap_pixels':len(a),'rgb_exact_pixels':int(np.all(a[:,:3]==c[:,:3],axis=1).sum()),
            'rgba_exact_pixels':int(np.all(a==c,axis=1).sum()),
            'rgb_mae':round(float(np.abs(a[:,:3]-c[:,:3]).mean()),6) if len(a) else None,
            'alpha_mae':round(float(np.abs(a[:,3]-c[:,3]).mean()),6) if len(a) else None}
