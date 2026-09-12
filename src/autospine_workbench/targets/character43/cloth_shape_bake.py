"""Bake the pinned cloth trial on top of existing deforms; validate between keys."""
from copy import deepcopy
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from .affine_pose import matrices, sample
from .cloth_shape_probe import probe
from .deformation_qa import inspect
from .deform_sum import combine


def bake(document, animation, helper, *, samples=65, extra_times=(), temporal=False, exact_temporal=False, continuation=False, material=False, material_subframes=False, target_prior=0.):
    if set(document['animations']) != {animation}: raise ValueError('cloth_shape_bake_single_clip')
    result = deepcopy(document); slot = helper.removeprefix('cloth-')
    attachment = document['skins'][0]['attachments'][slot][slot]
    previous = document['animations'][animation].get('attachments', {}).get('default', {}).get(
        slot, {}).get(slot, {}).get('deform')
    data = attachment['vertices']; keys = []
    def capture(time, points, fixed):
        transforms = matrices(document, animation, time)
        offsets = []; cursor = 0
        for p, q in zip(points, fixed):
            dx, dy = p[0]-q[0], p[1]-q[1]
            count = data[cursor]; cursor += 1
            for _ in range(count):
                bone = data[cursor]; cursor += 4
                a, b, c, d, _, _ = transforms[document['bones'][bone]['name']]
                det = a*d-b*c
                if abs(det) < 1e-10: raise ValueError('cloth_shape_bake_singular')
                offsets.extend(((d*dx-b*dy)/det, (a*dy-c*dx)/det))
        keys.append(dict(time=time, vertices=offsets))
    report = probe(document, animation, helper, samples=samples, constrained=True,
                   on_frame=capture, extra_times=extra_times, temporal=temporal, exact_temporal=exact_temporal,
                   continuation=continuation, material=material, material_subframes=material_subframes, target_prior=target_prior)
    # Add piecewise-linear timelines on their UNION, rather than resampling away old keys.
    # A zero correction then preserves non-cloth deform at every time, not just solver ticks.
    if previous:
        keys = combine(previous, keys)
    result['animations'][animation].setdefault('attachments', {}).setdefault('default', {}).setdefault(
        slot, {}).setdefault(slot, {})['deform'] = keys
    # Preserve every unrelated channel/clip. This tool expects a single-clip motion candidate.
    raw = canonical_bytes(result); duration = keys[-1]['time']
    times = sorted({k['time'] for k in keys} | {duration*i/1024 for i in range(1025)})
    reference = dict(skeleton_sha256=sha256(raw).hexdigest(), animations={animation: [
        dict(time=t, vertices=sample(result, animation, t)[0]) for t in times]})
    files = {'skeleton.json': raw, 'numeric-reference.json': canonical_bytes(reference)}
    qa = inspect(files)
    report.update(dense_sample_count=len(times), geometry_passed=qa['passed'],
                  baked_key_count=len(keys), existing_deform='linear_key_union_preserved')
    files.update({'cloth-shape.json': canonical_bytes(report), 'deformation.json': canonical_bytes(qa)})
    if material:
        from .cloth_strain_report import inspect as inspect_strain
        files['cloth-strain.json'] = canonical_bytes(inspect_strain(files, helper))
    return files
