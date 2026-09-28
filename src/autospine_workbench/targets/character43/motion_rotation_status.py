"""Read-only rotation diagnosis bound to an exact source and exported candidate."""
import json
import math

from ...motion_validation import motion_ir_sha256
from .motion_clip import boundaries, clip_motion
from .oblique_source import extract
from .oblique_motion import project
from .oblique_target import prepare
from .rotation_diagnostics import summarize
from .rotation_transfer_diagnostics import compare


def build(files, artifact, bundle, request):
    manifest = json.loads(files['character-manifest.json'])
    identity = request['motion_identity']
    if (manifest['source_motion_bundle_sha256'] != identity['bundle_sha256']
            or manifest['source_character_sha256'] != request['character_sha256']):
        raise ValueError('rotation_candidate_source_identity_mismatch')
    motion = bundle.motion
    camera=None
    yaw = request.get('projection', {}).get('yaw_degrees', 0)
    if request.get('projection') is not None:
        from .camera_track import PROFILE as CAMERA_PROFILE
        if request['projection'].get('profile')==CAMERA_PROFILE:
            from ...automation.motion_camera_pose import prepare as prepare_camera
            motion,_,camera=prepare_camera(bundle,request['projection']['keys'],sampling_profile=request['projection'].get('sampling_profile'))
        else:motion, _ = prepare(bundle, request['projection'])
    tracks = [r for r in motion['tracks'] if r['property'] == 'rotation']
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in r['keys']] != ticks for r in tracks):
        raise ValueError('rotation_source_sample_mismatch')
    bounds = boundaries(request.get('clip'), ticks)
    expected = clip_motion(motion, bounds)
    stored = json.loads(files['motion-ir.json'])
    if motion_ir_sha256(expected) != motion_ir_sha256(stored):
        raise ValueError('rotation_candidate_motion_identity_mismatch')
    vectors, _, _ = extract(bundle)
    if camera is not None:vectors=camera['vectors']
    indices = [i for i, tick in enumerate(ticks) if bounds is None or bounds[0] <= tick <= bounds[1]]
    origin = bounds[0] if bounds else 0
    times = [(ticks[i]-origin)/motion['ticks_per_second'] for i in indices]
    series = {}
    for role, values in vectors.items():
        if not role.startswith(('humanoid.arm.', 'humanoid.leg.')):
            continue
        if len(values) != len(ticks):
            raise ValueError('rotation_source_sample_mismatch')
        series[role] = [(project(values[i], yaw)[0], project(values[i], yaw)[1],
                         math.sqrt(sum(v*v for v in values[i]))) for i in indices]
    source = summarize(series, times)
    document = json.loads(files['skeleton.json'])
    names = manifest['animations']
    if len(names) != 1:
        raise ValueError('rotation_candidate_animation_ambiguous')
    target = compare(stored, document, names[0], source)
    return dict(profile='candidate-rotation-diagnostic-v1', artifact_sha256=artifact,
        source_job_id=request['source_job_id'], motion_identity=identity,
        projection=request.get('projection'), clip=request.get('clip'),
        source=source, target=target, authority='none', production_authorized=False,
        scope='sampled_direction_and_exported_local_rotation_not_visual_or_axial_twist',
        animation_modified=False)
