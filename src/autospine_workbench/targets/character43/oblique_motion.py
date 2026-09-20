"""Independent constant-yaw MotionIR candidates; existing map contracts stay intact."""
from copy import deepcopy
import math

from ...motion_roles import nearest_mapped_parent_role
from ...motion_validation import require_motion_ir, motion_ir_sha256
from ...resolved_project import canonical_sha256
from .projection_diagnostics import summarize

PROFILE = 'constant-yaw-source-motion-v1'


def project(point, yaw):
    angle=math.radians(yaw); c,s=math.cos(angle),math.sin(angle)
    x,y,z=point
    return c*x-s*z,y,s*x+c*z


def compile_candidate(base, vectors, roots, reference, yaw, *, precision=12):
    require_motion_ir(base)
    if type(precision) is not int or precision not in (5,12): raise ValueError('oblique_precision_invalid')
    if type(yaw) not in (int,float) or not math.isfinite(yaw) or not -90 <= yaw <= 90:
        raise ValueError('oblique_yaw_invalid')
    if not math.isfinite(reference) or reference <= 0: raise ValueError('oblique_reference_invalid')
    rotation_tracks={t['target']:t for t in base['tracks'] if t['property']=='rotation'}
    if set(rotation_tracks)!=set(vectors): raise ValueError('oblique_roles_mismatch')
    ticks=[k['tick'] for k in next(iter(rotation_tracks.values()))['keys']]
    if len(roots)!=len(ticks) or any([k['tick'] for k in t['keys']]!=ticks for t in rotation_tracks.values()):
        raise ValueError('oblique_samples_mismatch')
    if any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in roots):
        raise ValueError('oblique_root_invalid')
    angles={}; visibility={}
    for role, samples in vectors.items():
        if len(samples)!=len(ticks): raise ValueError('oblique_samples_mismatch')
        values=[]; ratios=[]
        for point in samples:
            if len(point)!=3 or any(not math.isfinite(v) for v in point): raise ValueError('oblique_vector_invalid')
            x,y,_=project(point,yaw); length=math.sqrt(sum(v*v for v in point))
            visible=math.hypot(x,y)
            if visible <= max(1e-12,length*1e-6,reference*1e-9):
                raise ValueError('oblique_projected_segment_degenerate:'+role)
            raw=math.degrees(math.atan2(y,x))
            values.append(raw if not values else values[-1]+(raw-values[-1]+180)%360-180)
            ratios.append(visible/length)
        angles[role]=[v-values[0] for v in values]
        if role.startswith(('humanoid.arm.','humanoid.leg.')): visibility[role]=ratios
    result=deepcopy(base)
    receipt=dict(profile=PROFILE,parent_motion_sha256=motion_ir_sha256(base),yaw_degrees=yaw,precision_decimals=precision,
                 spatial_input_sha256=canonical_sha256(dict(vectors=vectors,roots=roots,reference=reference)))
    result['clip_id']='oblique.'+canonical_sha256(receipt)[:32]
    for track in result['tracks']:
        if track['property']=='rotation':
            role=track['target']; parent=nearest_mapped_parent_role(role,angles)
            for i,key in enumerate(track['keys']):
                key['value']=round(angles[role][i]-(angles[parent][i] if parent else 0),precision)
        elif track['target']=='humanoid.root' and track['property']=='translation':
            if [k['tick'] for k in track['keys']]!=ticks: raise ValueError('oblique_root_ticks_mismatch')
            origin=project(roots[0],yaw)
            for key,point in zip(track['keys'],roots):
                p=project(point,yaw)
                key['value']=[round((p[i]-origin[i])/reference,precision) for i in (0,1)]
        else: raise ValueError('oblique_track_unsupported')
    require_motion_ir(result)
    receipt.update(motion_sha256=motion_ir_sha256(result),authority='none',
                   projection=summarize(visibility,[t/base['ticks_per_second'] for t in ticks]),
                   limitations=['constant_view_not_character_side_artwork',
                                'requires_new_target_contact_geometry_and_depth_validation'])
    return result,receipt
