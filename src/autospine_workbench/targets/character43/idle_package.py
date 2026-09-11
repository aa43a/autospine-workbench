"""Add the frozen MotionIR idle to an ordinary candidate without changing its rig."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from ...motion_builtin import build_builtin_motion
from ...automation.storage_io import canonical_bytes
from ..spine43.continuous_pose import world,interpolate

ROLES={'humanoid.root':'root','humanoid.head':'head','humanoid.spine.lower':'spine','humanoid.spine.upper':'chest'}


def append_idle(files,checkpoint=lambda:None):
    result=dict(files);doc=json.loads(files['skeleton.json']);manifest=json.loads(files['character-manifest.json'])
    if manifest['profile']!='ordinary-limb-flex-preserved-v1':raise ValueError('character_idle_source_unsupported')
    bones={b['name']:b for b in doc['bones']}
    if len(bones)!=len(doc['bones']) or not set(ROLES.values()).union({'calf_l','calf_r','foot_l','foot_r'})<=set(bones):
        raise ValueError('character_idle_bones_missing')
    if bones['root'].get('parent'):raise ValueError('character_idle_root_parent')
    for side in ('l','r'):
        if bones['calf_'+side].get('parent')!='thigh_'+side or bones['foot_'+side].get('parent')!='calf_'+side:
            raise ValueError('character_idle_leg_topology')
    # Same normalization method as the existing MotionIR target profile.
    length=sum(math.hypot(bones[n]['x'],bones[n]['y']) for n in ('calf_l','foot_l','calf_r','foot_r'))/2
    if not math.isfinite(length) or length<=0:raise ValueError('character_idle_reference_length')
    motion=build_builtin_motion('idle');animation={'bones':{}}
    for track in motion.document['tracks']:
        name=ROLES[track['target']];rotation=track['property']=='rotation';keys=[]
        for key in track['keys']:
            row={'time':key['tick']/motion.document['ticks_per_second']}
            if rotation:row['value']=-key['value']
            else:row.update(x=key['value'][0]*length,y=-key['value'][1]*length)
            keys.append(row)
        animation['bones'].setdefault(name,{})['rotate' if rotation else 'translate']=keys
    if 'idle' in doc['animations']:raise ValueError('character_idle_duplicate')
    doc['animations']['idle']=animation
    result['skeleton.json']=canonical_bytes(doc)
    if 'editor/skeleton.json' in result:result['editor/skeleton.json']=result['skeleton.json']
    reference=json.loads(files['numeric-reference.json']);frames=[]
    single=deepcopy(doc);single['animations']={'idle':animation}
    for tick in range(129):
        if tick%16==0:checkpoint()
        time=tick/64;pose=deepcopy(single)
        for b in pose['bones']:
            keys=animation['bones'].get(b['name'],{}).get('translate')
            if keys:
                vector=interpolate([dict(time=k['time'],vertices=[k['x'],k['y']]) for k in keys],time,'vertices')
                b['x']+=vector[0];b['y']+=vector[1]
        frames.append(dict(time=time,vertices=world(pose,time)))
    reference['animations']['idle']=frames;reference['skeleton_sha256']=sha256(result['skeleton.json']).hexdigest()
    result['numeric-reference.json']=canonical_bytes(reference)
    result['idle-motion-ir.json']=motion.canonical_json.encode()
    manifest.update(profile='ordinary-motionir-idle-v1',animations=list(doc['animations']))
    manifest['idle_retarget']=dict(motion_sha256=motion.sha256,reference_length_px=length,
                                  normalization='mean-leg-maximum-kinematic-reach',contact_mode='annotation_only')
    manifest['files']={n:sha256(raw).hexdigest() for n,raw in sorted(result.items()) if n!='character-manifest.json'}
    result['character-manifest.json']=canonical_bytes(manifest)
    return result
