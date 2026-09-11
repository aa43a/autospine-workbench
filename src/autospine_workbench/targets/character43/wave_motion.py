"""Frozen MotionIR wave mapped onto reviewed canonical workbench arm geometry."""
from copy import deepcopy
import math
from ...ik_setup_local import solve_setup_local_ik
from ...motion_builtin import build_builtin_motion
from ..spine43.continuous_pose import interpolate


def pose(bones,rotations=None):
    result={};rotations=rotations or {}
    for b in bones:
        x,y,a=result[b['parent']] if b.get('parent') else (0,0,0)
        radians=math.radians(a);dx=b['x'];dy=b['y']
        result[b['name']]=(x+dx*math.cos(radians)-dy*math.sin(radians),y+dx*math.sin(radians)+dy*math.cos(radians),a+b['rotation']+rotations.get(b['name'],0))
    return result


def build_wave(document):
    bones={b['name']:b for b in document['bones']}
    required={'pelvis','chest','clavicle_l','upperarm_l','forearm_l','hand_l','upperarm_r'}
    if not required<=set(bones) or len(bones)!=len(document['bones']):raise ValueError('character_wave_bones_missing')
    for child,parent in [('clavicle_l','chest'),('upperarm_l','clavicle_l'),('forearm_l','upperarm_l'),('hand_l','forearm_l')]:
        if bones[child].get('parent')!=parent:raise ValueError('character_wave_arm_topology')
    if any(abs(bones[n]['y'])>1e-6 or bones[n]['x']<=0 for n in ('forearm_l','hand_l')):
        raise ValueError('character_wave_nonaxial_arm')
    setup=pose(document['bones'])
    def unit(x,y):
        length=math.hypot(x,y)
        if not math.isfinite(length) or length<1e-8:raise ValueError('character_wave_body_frame_degenerate')
        return x/length,y/length
    pelvis=setup['pelvis'];chest=setup['chest'];up=unit(chest[0]-pelvis[0],chest[1]-pelvis[1])
    def outward(name):
        p=setup[name];x=p[0]-chest[0];y=p[1]-chest[1];dot=x*up[0]+y*up[1]
        return unit(x-dot*up[0],y-dot*up[1])
    left=outward('upperarm_l');right=outward('upperarm_r')
    if sum(a*b for a,b in zip(left,right))>-.5:raise ValueError('character_wave_side_frame_ambiguous')
    motion=build_builtin_motion('wave.left');source=motion.document
    rotation,handle=source['tracks'];clavicle=[dict(time=k['tick']/source['ticks_per_second'],value=-k['value']) for k in rotation['keys']]
    animation={'bones':{'clavicle_l':{'rotate':clavicle},'upperarm_l':{'rotate':[]},'forearm_l':{'rotate':[]}}};evidence=[]
    proximal=bones['forearm_l']['x'];distal=bones['hand_l']['x'];reach=proximal+distal
    bend=math.sin(math.radians(bones['forearm_l']['rotation']))
    if abs(bend)<1e-7:raise ValueError('character_wave_bend_ambiguous')
    for key in handle['keys']:
        time=key['tick']/source['ticks_per_second'];ancestor=interpolate(clavicle,time,'value')
        current=pose(document['bones'],{'clavicle_l':ancestor});root=current['upperarm_l'];hand=current['hand_l']
        v=key['value'];target=hand[:2] if v=='setup' else (root[0]+reach*(left[0]*v[0]+up[0]*v[1]),root[1]+reach*(left[1]*v[0]+up[1]*v[1]))
        solved=solve_setup_local_ik(root[:2],proximal_length=proximal,distal_length=distal,target_xy=target,
            bend_direction='negative' if bend>0 else 'positive',fallback_direction_xy=(hand[0]-root[0],hand[1]-root[1]),
            setup_proximal_world_rotation_deg=root[2],setup_distal_local_rotation_deg=bones['forearm_l']['rotation'])
        if solved.world.reach_state!='reachable':raise ValueError('character_wave_target_unreachable')
        angles=(solved.proximal_rotation_delta_deg,solved.distal_rotation_delta_deg)
        if v=='setup' and max(abs(a) for a in angles)>1e-6:raise ValueError('character_wave_setup_branch_mismatch')
        for name,value in zip(('upperarm_l','forearm_l'),angles):animation['bones'][name]['rotate'].append(dict(time=time,value=0. if v=='setup' else value))
        endpoint=pose(document['bones'],{'clavicle_l':ancestor,'upperarm_l':angles[0],'forearm_l':angles[1]})['hand_l']
        error=math.dist(endpoint[:2],target)
        if error>1e-6:raise ValueError('character_wave_ik_endpoint_mismatch')
        evidence.append(dict(time=time,target=list(target),endpoint_error_px=error,reach_state=solved.world.reach_state))
    for tracks in animation['bones'].values():
        if any(abs(a['value']-b['value'])>180 for a,b in zip(tracks['rotate'],tracks['rotate'][1:])):
            raise ValueError('character_wave_rotation_branch_jump')
    result=deepcopy(document);result['animations']={'wave-left':animation}
    return result,dict(profile='canonical-arm-motionir-wave-v1',motion_sha256=motion.sha256,authority='none',
                       up=list(up),left_outward=list(left),ik_keys=evidence,contact_mode='annotation_only')
