"""Bilinear sampled corrective field, baked to linear 30 FPS keys."""
from copy import deepcopy
import math
from ...asset.joints.combined_corrective import POSES
from .continuous_pose import inspect


def blend(grid,main,distal):
    if not (math.isfinite(main) and math.isfinite(distal) and 0<=main<=60 and -30<=distal<=30):
        raise ValueError('continuous_angle_outside_profile')
    a=0 if main<=30 else 30;b=-30 if distal<=0 else 0
    u=(main-a)/30;v=(distal-b)/30
    corners=[grid[(a,b)],grid[(a+30,b)],grid[(a,b+30)],grid[(a+30,b+30)]]
    if len({len(c) for c in corners})!=1:raise ValueError('continuous_offset_length_mismatch')
    return [sum(w*c[i] for w,c in zip(((1-u)*(1-v),u*(1-v),(1-u)*v,u*v),corners)) for i in range(len(corners[0]))]


def bake(source):
    if set(source['animations'])!={'combined-pose-inspection'}:raise ValueError('continuous_source_animation_invalid')
    doc=deepcopy(source);old=source['animations']['combined-pose-inspection'];bones={};attachments={}
    poses=[(i/30,30*(1-math.cos(math.pi*i/30)),30*math.sin(math.pi*i/30)) for i in range(61)]
    poses[0]=(0,0,0);poses[-1]=(2,0,0)
    for name,track in old['bones'].items():
        values=[k['value'] for k in track['rotate']]
        axes=[axis for axis in (0,1) if values==[-p[axis] for p in POSES]]
        if len(axes)!=1:raise ValueError('continuous_bone_track_invalid')
        axis=axes[0];bones[name]={'rotate':[{'time':t,'value':-(a if axis==0 else b)} for t,a,b in poses]}
    for name,slot in old['attachments']['default'].items():
        keys=slot[name]['deform']
        if len(keys)!=len(POSES):raise ValueError('continuous_pose_count_invalid')
        grid={pose:key['vertices'] for pose,key in zip(POSES,keys)}
        attachments[name]={name:{'deform':[{'time':t,'vertices':blend(grid,a,b)} for t,a,b in poses]}}
    doc['animations']={'continuous-corrective-inspection':{'bones':bones,'attachments':{'default':attachments}}}
    return doc,inspect(doc)
