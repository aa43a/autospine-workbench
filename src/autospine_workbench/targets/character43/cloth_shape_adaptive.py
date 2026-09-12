"""Bounded diagnostic re-bake at actual interpolation failures, with a denser check grid."""
import json
from ...asset.planning.component_local_solver import metrics
from ...automation.storage_io import canonical_bytes
from .cloth_shape_bake import bake


def build(document, animation, helper, *, samples=65, rounds=3, progress=None, temporal=False, exact_temporal=False, continuation=False, material=False):
    if type(rounds) is not int or not 1 <= rounds <= 4:
        raise ValueError('cloth_shape_adaptive_rounds')
    extra = set(); history = []; slot = helper.removeprefix('cloth-')
    flat = document['skins'][0]['attachments'][slot][slot]['triangles']
    triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
    for step in range(rounds):
        files = bake(document, animation, helper, samples=samples, extra_times=sorted(extra), temporal=temporal, exact_temporal=exact_temporal, continuation=continuation, material=material)
        qa = json.loads(files['deformation.json']); report = json.loads(files['cloth-shape.json'])
        frames = json.loads(files['numeric-reference.json'])['animations'][animation]
        setup = frames[0]['vertices'][slot]
        failed = [f['time'] for f in frames if metrics(setup, f['vertices'][slot], triangles)['bad_triangles']]
        history.append(dict(round=step, key_count=report['sample_count'],
                            checked_frames=len(frames), failing_times=failed, geometry_passed=qa['passed']))
        if progress: progress(history[-1])
        new = set(failed)-extra
        if qa['passed'] or not new or len(extra | new) > 257: break
        extra.update(new)
    files['cloth-adaptive.json'] = canonical_bytes(dict(profile='cloth-failed-time-refinement-v1',
        authority='none', selected=False, rounds=history, geometry_passed=qa['passed'],
        limitation='sampled_validation_not_continuous_time_proof'))
    return files
