"""Versioned source-pose experiment alongside unchanged legacy target preparation."""
from ..motion_validation import motion_ir_sha256

PROFILE = 'absolute-projection-temporal-corrective-v1'


def prepare(bundle):
    from ..targets.character43.oblique_source import extract
    vectors,_,_=extract(bundle)
    motion=bundle.motion
    tracks=[t for t in motion['tracks'] if t['property']=='rotation']
    if not tracks:
        raise ValueError('source_pose_profile_rotation_tracks_required')
    ticks=[k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']]!=ticks for t in tracks):
        raise ValueError('source_pose_profile_samples_mismatch')
    return dict(profile=PROFILE,motion_sha256=motion_ir_sha256(motion),vectors=vectors,
                times=[t/motion['ticks_per_second'] for t in ticks])


def project(document,name,motion,bvh,mapping,kimodo,oblique,time_range,pose_fit):
    if pose_fit is not None:
        if (pose_fit.get('profile')!=PROFILE or pose_fit.get('motion_sha256')!=motion_ir_sha256(motion)
                or oblique is not None):
            raise ValueError('source_pose_profile_identity_or_view_mismatch')
        from ..targets.character43.source_pose_fit import fit
        document,evidence=fit(document,name,pose_fit['vectors'],pose_fit['times'],project_lengths=True)
        evidence['target_profile']=PROFILE
        return document,evidence
    if oblique is not None:
        from ..targets.character43.oblique_target import lengths
        return lengths(document,name,oblique,time_range=time_range)
    if kimodo is None:
        from ..targets.character43.projected_lengths import build
        return build(document,name,bvh,mapping,time_range=time_range)
    from ..targets.character43.kimodo_lengths import build
    return build(document,name,*kimodo,mapping,time_range=time_range)


def correct(document,name,setup_vertices,pose_fit):
    if pose_fit is not None:
        from ..targets.character43.projected_area_adaptive import build
        return build(document,name,setup_vertices,temporal=True)
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
