"""Bake a bounded torso-plane warp, keeping arm/head linear transforms intact."""
from copy import deepcopy
import math

from .affine_pose import matrices
from ..spine43.continuous_pose import interpolate

PROFILE = 'torso-plane-compensated-deform-v1-experiment'


def multiply(a,b):
    aa,ab,ac,ad,ax,ay=a; ba,bb,bc,bd,bx,by=b
    return (aa*ba+ab*bc,aa*bb+ab*bd,ac*ba+ad*bc,ac*bb+ad*bd,
            ax+aa*bx+ab*by,ay+ac*bx+ad*by)


def inverse(m):
    a,b,c,d,x,y=m; det=a*d-b*c
    if det <= 1e-10: raise ValueError('torso_transform_degenerate')
    return (d/det,-b/det,-c/det,a/det,(b*y-d*x)/det,(c*x-a*y)/det)


def point(m,x,y):
    a,b,c,d,tx,ty=m
    return tx+a*x+b*y,ty+c*x+d*y


def transformed(document, baseline, shape):
    result = {}
    for bone in document['bones']:
        name = bone['name']; old = baseline[name]; parent = bone.get('parent')
        if name == 'chest':
            result[name] = multiply(old,(shape[0],shape[1],0,shape[2],0,0))
        elif parent:
            result[name] = multiply(result[parent],multiply(inverse(baseline[parent]),old))
            if name in ('neck','upperarm_l','upperarm_r'):
                result[name] = (*old[:4],*result[name][4:])
        else:
            result[name] = old
    return result


def build(document, animation, report, *, samples=129):
    if report['profile'] != 'source-torso-plane-shape-v1-experiment':
        raise ValueError('torso_shape_profile_unsupported')
    rows = report['records']; rejected = [r for r in rows if r['reasons']]
    if (len(rows)<2 or any(not math.isfinite(r[k]) for r in rows
            for k in ('time','longitudinal','transverse','shear','visibility'))
            or any(b['time']<=a['time'] for a,b in zip(rows,rows[1:]))):
        raise ValueError('torso_shape_records_invalid')
    receipt = dict(profile=PROFILE,authority='none',selected=False,production_authorized=False,
        failures=rejected,source=report,scope='baked_visual_candidate_bone_guides_unchanged',
        limitations=['requires_new_geometry_contact_depth_and_runtime_checks',
                     'no_side_back_artwork_generation','planar_torso_not_surface_reconstruction'])
    if rejected: return None,dict(receipt,status='source_projection_unsupported')
    if any(not (.75<=r['longitudinal']<=1.25 and .5<=r['transverse']<=1.5
                and abs(r['shear'])<=.5 and r['visibility']>=.2) for r in rows):
        raise ValueError('torso_shape_limits_mismatch')
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('torso_sample_limit')
    names = {b['name'] for b in document['bones']}
    if not {'chest','neck','upperarm_l','upperarm_r'} <= names:
        raise ValueError('torso_target_anchors_missing')
    parents={b['name']:b.get('parent') for b in document['bones']}
    for name in ('neck','upperarm_l','upperarm_r'):
        seen=set()
        while name and name!='chest' and name not in seen:
            seen.add(name);name=parents.get(name)
        if name!='chest': raise ValueError('torso_target_topology_unsupported')
    original = document['animations'][animation]
    duration = rows[-1]['time']
    if rows[0]['time'] != 0 or duration <= 0:
        raise ValueError('torso_candidate_time_invalid')
    shape_keys = [dict(time=r['time'],vertices=[r['longitudinal'],r['shear'],r['transverse']]) for r in rows]
    times = sorted({r['time'] for r in rows} | {duration*i/(samples-1) for i in range(samples)} |
        {k['time'] for tracks in original.get('bones',{}).values() for keys in tracks.values() for k in keys} |
        {k['time'] for slots in original.get('attachments',{}).values() for choices in slots.values()
         for props in choices.values() for keys in props.values() for k in keys})
    if len(times)>2049 or times[-1]>duration: raise ValueError('torso_candidate_time_limit')
    result = deepcopy(document); output = result['animations'][animation]
    changes = {}; slot_changes = {}; bones = document['bones']; maximum = 0.
    for time in times:
        old = matrices(document,animation,time)
        new = transformed(document,old,interpolate(shape_keys,time,'vertices'))
        local = {n:multiply(inverse(old[n]),m) for n,m in new.items()}
        for slot,choices in document['skins'][0]['attachments'].items():
            attachment = choices[slot]; data = attachment['vertices']
            keys = original.get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform')
            previous = interpolate(keys,time,'vertices') if keys else []
            offsets = []; i=j=0
            while i<len(data):
                count=data[i];i+=1
                for _ in range(count):
                    index,x,y,_=data[i:i+4];i+=4; name=bones[index]['name']
                    px,py=(previous[j:j+2] if previous else (0.,0.));j+=2
                    nx,ny=point(local[name],x+px,y+py)
                    offsets.extend((nx-x,ny-y))
                    displacement=math.dist(point(old[name],x+px,y+py),point(new[name],x+px,y+py))
                    maximum=max(maximum,displacement)
                    slot_changes[slot]=max(slot_changes.get(slot,0),displacement)
            changes.setdefault(slot,[]).append(dict(time=time,vertices=offsets))
    for slot,keys in changes.items():
        if slot_changes[slot] < 1e-8: continue
        output.setdefault('attachments',{}).setdefault('default',{})[slot]={slot:{'deform':keys}}
    return result,dict(receipt,status='candidate_requires_validation',sample_count=len(times),
                       maximum_influence_displacement_px=maximum,changed_slots=[s for s,v in slot_changes.items() if v>=1e-8])
