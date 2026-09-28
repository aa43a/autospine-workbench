"""Versioned source-pose experiment alongside unchanged legacy target preparation."""
from ..motion_validation import motion_ir_sha256

PROFILE = 'absolute-projection-temporal-corrective-v1'
HIP_PROFILE = 'absolute-projection-hip-center-temporal-v1'


def prepare(bundle, *, hip_center=False):
    from ..targets.character43.oblique_source import extract
    vectors,_,_=extract(bundle)
    motion=bundle.motion
    tracks=[t for t in motion['tracks'] if t['property']=='rotation']
    if not tracks:
        raise ValueError('source_pose_profile_rotation_tracks_required')
    ticks=[k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']]!=ticks for t in tracks):
        raise ValueError('source_pose_profile_samples_mismatch')
    result=dict(profile=HIP_PROFILE if hip_center else PROFILE,motion_sha256=motion_ir_sha256(motion),vectors=vectors,
                times=[t/motion['ticks_per_second'] for t in ticks])
    if hip_center:
        from ..targets.character43.source_hip_centers import extract as hip_centers
        result['hip_centers'],result['source_reference']=hip_centers(bundle)
    return result


def project(document,name,motion,bvh,mapping,kimodo,oblique,time_range,pose_fit):
    if pose_fit is not None:
        from ..targets.character43.camera_track import PROFILE as CAMERA_PROFILE
        if pose_fit.get('profile') == CAMERA_PROFILE:
            if time_range is not None:raise ValueError('camera_pose_requires_full_clip')
            from .motion_camera_pose import fit as camera_fit
            return camera_fit(document,name,motion,oblique,pose_fit)
        from .motion_view_pose import PROFILE as VIEW_PROFILE, validate as validate_view
        if pose_fit.get('profile') == VIEW_PROFILE:
            validate_view(pose_fit,motion,oblique,time_range)
        elif (pose_fit.get('profile') not in (PROFILE,HIP_PROFILE) or pose_fit.get('motion_sha256')!=motion_ir_sha256(motion)
                or oblique is not None):
            raise ValueError('source_pose_profile_identity_or_view_mismatch')
        from ..targets.character43.source_pose_fit import fit
        document,evidence=fit(document,name,pose_fit['vectors'],pose_fit['times'],project_lengths=True)
        if pose_fit['profile'] in (HIP_PROFILE,VIEW_PROFILE):
            import math
            from ..targets.character43.hip_center_motion import apply
            bones={b['name']:b for b in document['bones']}
            reference=sum(math.hypot(bones[n]['x'],bones[n]['y']) for n in ('calf_l','foot_l','calf_r','foot_r'))/2
            document,evidence['hip_center']=apply(document,name,pose_fit['hip_centers'],pose_fit['times'],
                                                 pose_fit['source_reference'],reference)
            evidence['limb_output_sha256']=evidence['output_sha256']
            evidence['output_sha256']=evidence['hip_center']['output_sha256']
        evidence['target_profile']=pose_fit['profile']
        return document,evidence
    if oblique is not None:
        from ..targets.character43.oblique_target import lengths
        return lengths(document,name,oblique,time_range=time_range)
    if kimodo is None:
        from ..targets.character43.projected_lengths import build
        return build(document,name,bvh,mapping,time_range=time_range)
    from ..targets.character43.kimodo_lengths import build
    return build(document,name,*kimodo,mapping,time_range=time_range)


def correct(document,name,setup_vertices,pose_fit,on_stage=None):
    if pose_fit is not None:
        from ..targets.character43.projected_area_adaptive import build
        return build(document,name,setup_vertices,temporal=True,
                     **({'progress':lambda detail:on_stage(dict(step='retarget', detail=detail))} if on_stage else {}))
    from ..targets.character43.affine_area_repair import repair
    return repair(document,name,samples=129,convergent=True,setup_vertices=setup_vertices)


def final_times(document,name,times):
    animation=document['animations'][name]
    keys={k['time'] for tracks in animation['bones'].values() for values in tracks.values() for k in values}
    keys.update(k['time'] for skin in animation.get('attachments',{}).values() for slots in skin.values()
                for tracks in slots.values() for values in tracks.values() for k in values)
    keys=sorted(keys|set(times))
    result=sorted(set(keys)|{(a+b)/2 for a,b in zip(keys,keys[1:])})
    if len(result)>4097:
        raise ValueError('source_pose_final_sample_limit')
    return result
