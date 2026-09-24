"""Bind knee observations to the candidate's exact source, view and clip."""
import json
from ...motion_validation import motion_ir_sha256
from .motion_clip import boundaries, clip_motion
from .oblique_source import extract
from .oblique_target import prepare


def read(files, bundle, request):
    manifest = json.loads(files['character-manifest.json'])
    identity = request['motion_identity']
    if (manifest['source_motion_bundle_sha256'] != identity['bundle_sha256']
            or manifest['source_character_sha256'] != request['character_sha256']):
        raise ValueError('knee_candidate_source_identity_mismatch')
    motion = bundle.motion
    if request.get('projection') is not None:
        motion, _ = prepare(bundle, request['projection'])
    tracks = [t for t in motion['tracks'] if t['property'] == 'rotation']
    if not tracks:
        raise ValueError('knee_source_sample_mismatch')
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']] != ticks for t in tracks):
        raise ValueError('knee_source_sample_mismatch')
    bounds = boundaries(request.get('clip'), ticks)
    if motion_ir_sha256(clip_motion(motion, bounds)) != motion_ir_sha256(json.loads(files['motion-ir.json'])):
        raise ValueError('knee_candidate_motion_identity_mismatch')
    vectors, _, _ = extract(bundle)
    if any(len(v) != len(ticks) for v in vectors.values()):
        raise ValueError('knee_source_sample_mismatch')
    indices = [i for i,t in enumerate(ticks) if bounds is None or bounds[0] <= t <= bounds[1]]
    origin = bounds[0] if bounds else 0
    times = [(ticks[i]-origin)/motion['ticks_per_second'] for i in indices]
    source_times = [ticks[i]/motion['ticks_per_second'] for i in indices]
    names = manifest['animations']
    if len(names) != 1:
        raise ValueError('knee_candidate_animation_ambiguous')
    return names[0], {r:[values[i] for i in indices] for r,values in vectors.items()}, times, source_times
