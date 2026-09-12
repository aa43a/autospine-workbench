"""Bake the pinned cloth trial on top of existing deforms; validate between keys."""
from copy import deepcopy
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from ..spine43.continuous_pose import interpolate
from .affine_pose import matrices, sample
from .cloth_shape_probe import probe
from .deformation_qa import inspect


def bake(document, animation, helper, *, samples=65, extra_times=()):
    if set(document['animations']) != {animation}: raise ValueError('cloth_shape_bake_single_clip')
    result = deepcopy(document); slot = helper.removeprefix('cloth-')
    attachment = document['skins'][0]['attachments'][slot][slot]
    previous = document['animations'][animation].get('attachments', {}).get('default', {}).get(
        slot, {}).get(slot, {}).get('deform')
    data = attachment['vertices']; keys = []
    def capture(time, points, fixed):
        transforms = matrices(document, animation, time)
        old = interpolate(previous, time, 'vertices') if previous else []
        offsets = []; cursor = 0; offset = 0
        for p, q in zip(points, fixed):
            dx, dy = p[0]-q[0], p[1]-q[1]
            count = data[cursor]; cursor += 1
            for _ in range(count):
                bone = data[cursor]; cursor += 4
                a, b, c, d, _, _ = transforms[document['bones'][bone]['name']]
                det = a*d-b*c
                if abs(det) < 1e-10: raise ValueError('cloth_shape_bake_singular')
                offsets.extend(((old[offset] if old else 0)+(d*dx-b*dy)/det,
                                (old[offset+1] if old else 0)+(a*dy-c*dx)/det))
                offset += 2
        keys.append(dict(time=time, vertices=offsets))
    report = probe(document, animation, helper, samples=samples, constrained=True,
                   on_frame=capture, extra_times=extra_times)
    result['animations'][animation].setdefault('attachments', {}).setdefault('default', {}).setdefault(
        slot, {}).setdefault(slot, {})['deform'] = keys
    # Preserve every unrelated channel/clip. This tool expects a single-clip motion candidate.
    raw = canonical_bytes(result); duration = keys[-1]['time']
    times = sorted({k['time'] for k in keys} | {duration*i/1024 for i in range(1025)})
    reference = dict(skeleton_sha256=sha256(raw).hexdigest(), animations={animation: [
        dict(time=t, vertices=sample(result, animation, t)[0]) for t in times]})
    files = {'skeleton.json': raw, 'numeric-reference.json': canonical_bytes(reference)}
    qa = inspect(files)
    report.update(dense_sample_count=len(times), geometry_passed=qa['passed'])
    files.update({'cloth-shape.json': canonical_bytes(report), 'deformation.json': canonical_bytes(qa)})
    return files
