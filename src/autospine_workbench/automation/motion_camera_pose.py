"""Shared dynamic-camera preparation for editor preview and candidate baking.

Does not publish or accept a candidate. Callers must run geometry/contact/depth
and Runtime checks on any resulting target animation.
"""
from ..motion_validation import motion_ir_sha256
from ..resolved_project import canonical_sha256
from ..targets.character43.camera_projection import prepare as project_camera
from ..targets.character43.camera_track import PROFILE
from ..targets.character43.oblique_motion import compile_candidate
from ..targets.character43.oblique_source import extract
from ..targets.character43.source_hip_centers import extract as hip_centers


def prepare(bundle, keys, *, sampling_profile=None):
    vectors, roots, reference = extract(bundle)
    centers, hip_reference = hip_centers(bundle)
    if hip_reference != reference:
        raise ValueError('camera_source_reference_mismatch')
    base = bundle.motion
    tracks = [t for t in base['tracks'] if t['property'] == 'rotation']
    if not tracks:
        raise ValueError('camera_rotation_tracks_required')
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in track['keys']] != ticks for track in tracks):
        raise ValueError('camera_motion_samples_mismatch')
    times = [t/base['ticks_per_second'] for t in ticks]
    duration = base['duration_ticks']/base['ticks_per_second']
    compile_base=base
    sampling=None
    if sampling_profile is not None:
        from ..targets.character43.camera_sampling import PROFILE as SAMPLING, schedule,interpolate,motion_grid
        if sampling_profile!=SAMPLING:raise ValueError('camera_sampling_profile_unsupported')
        wanted=schedule(times,keys,duration)
        sampling=dict(profile=SAMPLING,source_samples=len(times),output_samples=len(wanted),
            source_times_sha256=canonical_sha256(times),scope='interpolated_world_observations_not_new_measurements')
        compile_base=motion_grid(base,times,wanted)
        vectors={role:interpolate(values,times,wanted) for role,values in vectors.items()}
        roots=interpolate(roots,times,wanted);centers=interpolate(centers,times,wanted);times=wanted
    camera = project_camera(vectors, roots, centers, times, reference, keys, duration)
    if sampling is not None:
        camera['sampling']=sampling
        camera['projection_sha256']=canonical_sha256({k:v for k,v in camera.items() if k!='projection_sha256'})
    if camera['temporal_issues']:
        raise ValueError('camera_sampling_insufficient')
    # The camera snapshot has already projected every frame into the final
    # basis. Reuse the existing angle/local-parent compiler at zero extra yaw.
    motion, compiled = compile_candidate(compile_base, camera['vectors'], camera['roots'], reference, 0,
        precision=5 if bundle.source_kind == 'kimodo_npz' else 12)
    identity = dict(profile=PROFILE, parent_motion_sha256=motion_ir_sha256(base),
                    camera_projection_sha256=camera['projection_sha256'])
    motion['clip_id'] = 'camera.'+canonical_sha256(identity)[:32]
    receipt = dict(**identity, motion_sha256=motion_ir_sha256(motion), keys=camera['keys'],
        projection=compiled['projection'], precision_decimals=compiled['precision_decimals'],
        spatial_input_sha256=camera['input_sha256'], authority='none',
        limitations=['source_projection_not_reconstructed_character_surface',
                     'requires_new_target_contact_geometry_depth_and_runtime_checks'])
    if sampling_profile is not None:receipt['sampling_profile']=sampling_profile
    return motion, receipt, camera


def validate(motion, receipt, camera):
    from ..targets.character43.camera_track import validate as validate_keys, at_times
    duration=motion['duration_ticks']/motion['ticks_per_second']
    validate_keys(camera['keys'],duration)
    payload={k:v for k,v in camera.items() if k!='projection_sha256'}
    if (camera.get('profile')!=PROFILE or receipt.get('profile')!=PROFILE
            or canonical_sha256(payload)!=camera.get('projection_sha256')
            or receipt.get('camera_projection_sha256')!=camera.get('projection_sha256')
            or receipt.get('motion_sha256')!=motion_ir_sha256(motion)
            or receipt.get('sampling_profile')!=camera.get('sampling',{}).get('profile')
            or receipt.get('keys')!=camera['keys']
            or camera['yaw_degrees']!=at_times(camera['keys'],camera['times'],duration)):
        raise ValueError('camera_pose_identity_mismatch')


def fit(document, name, motion, receipt, camera):
    """Produce the same baked pose for interactive sampling and final checks."""
    import math
    from ..targets.character43.source_pose_fit import fit as fit_limbs
    from ..targets.character43.hip_center_motion import apply as fit_hips
    validate(motion, receipt, camera)
    result, evidence = fit_limbs(document, name, camera['vectors'], camera['times'], project_lengths=True)
    bones = {b['name']:b for b in result['bones']}
    reference = sum(math.hypot(bones[n]['x'],bones[n]['y']) for n in ('calf_l','foot_l','calf_r','foot_r'))/2
    result, hips = fit_hips(result,name,camera['hip_centers'],camera['times'],camera['reference'],reference)
    evidence.update(target_profile=PROFILE, camera_projection_sha256=camera['projection_sha256'],
                    limb_output_sha256=evidence['output_sha256'], output_sha256=hips['output_sha256'],
                    hip_center=hips, surface_issues=camera['surface_issues'])
    return result,evidence
