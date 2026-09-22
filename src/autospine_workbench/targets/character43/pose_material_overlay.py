"""Experimental bend-gated material overlays, keeping the original bind image."""
from copy import deepcopy
import math
from .affine_pose import matrices


def activation(angle, start=30., full=70.):
    if not all(math.isfinite(v) for v in (angle,start,full)) or not 0<=start<full<=180:
        raise ValueError('pose_material_activation')
    t=max(0.,min(1.,(abs(angle)-start)/(full-start)))
    return t*t*(3-2*t)


def build(original, variant, regions, times, animation='external-motion'):
    if (original['bones']!=variant['bones'] or original['animations']!=variant['animations']
            or not times or times[0]!=0 or any(not math.isfinite(t) or t<0 for t in times)
            or times!=sorted(set(times))):raise ValueError('pose_material_source')
    doc=deepcopy(original);motion=doc['animations'][animation]
    if motion.get('drawOrder'):raise ValueError('pose_material_draw_order_unsupported')
    rest=matrices(dict(original,animations={'setup':{}}),'setup',0)
    current=[matrices(original,animation,t) for t in times];records=[]
    def angle(pose,bone):
        m=pose[bone];return math.degrees(math.atan2(m[2],m[0]))
    for region in regions:
        slot,joint=region['slot'],region['joint'];name=slot+'-pose-material'
        if any(s['name']==name for s in doc['slots']):raise ValueError('pose_material_collision')
        parent=next(b['parent'] for b in doc['bones'] if b['name']==joint)
        mesh=original['skins'][0]['attachments'][slot][slot]
        changed=deepcopy(variant['skins'][0]['attachments'][slot][slot])
        if {k:v for k,v in mesh.items() if k!='uvs'}!={k:v for k,v in changed.items() if k!='uvs'}:
            raise ValueError('pose_material_non_uv_change')
        moved={i for i in range(len(mesh['uvs'])//2)
               if max(abs(mesh['uvs'][i*2+j]-changed['uvs'][i*2+j]) for j in (0,1))>1e-10}
        selected=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)
                  if any(v in moved for v in mesh['triangles'][i:i+3])]
        if not selected:raise ValueError('pose_material_empty_region')
        changed.update(path=mesh.get('path',slot),triangles=[v for t in selected for v in t])
        changed.pop('hull',None);changed.pop('edges',None)
        doc['skins'][0]['attachments'][name]={name:changed}
        index=next(i for i,s in enumerate(doc['slots']) if s['name']==slot)
        old=doc['slots'][index]
        if old.get('color','ffffffff')!='ffffffff' or old.get('blend','normal')!='normal':
            raise ValueError('pose_material_slot_style')
        doc['slots'].insert(index+1,dict(old,name=name,attachment=name,color='ffffff00'))
        rest_angle=angle(rest,joint)-angle(rest,parent);keys=[]
        for time,pose in zip(times,current):
            delta=(angle(pose,joint)-angle(pose,parent)-rest_angle+180)%360-180
            keys.append(dict(time=time,value=activation(delta)))
        if keys[0]['value']!=0:raise ValueError('pose_material_initial_pose_not_neutral')
        motion.setdefault('slots',{})[name]={'alpha':keys}
        source=motion.get('attachments',{}).get('default',{}).get(slot,{}).get(slot)
        if source is not None:
            motion.setdefault('attachments',{}).setdefault('default',{})[name]={name:deepcopy(source)}
        records.append(dict(slot=slot,overlay=name,joint=joint,triangle_count=len(selected),
                            alpha_keys=keys,activation_degrees=[30,70]))
    return doc,dict(profile='bend-gated-source-uv-overlay-v1-experiment',records=records,
                    authority='none',selected=False,limitation='overlap_and_line_ghosting_require_raster_review')
