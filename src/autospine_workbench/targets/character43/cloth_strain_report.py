"""Material distortion diagnostics for the actual baked reference frames."""
import json
from hashlib import sha256
from ...asset.planning.cloth_strain import prepare, stretches
from .numeric_reference import read


def inspect(files, helper):
    import numpy as np
    document = json.loads(files['skeleton.json']); slot = helper.removeprefix('cloth-')
    attachment = document['skins'][0]['attachments'][slot][slot]
    data = attachment['vertices']; cursor = 0; free = set(); index = 0
    while cursor < len(data):
        count = data[cursor]; cursor += 1
        for _ in range(count):
            bone, _, _, w = data[cursor:cursor+4]; cursor += 4
            if document['bones'][bone]['name'] == helper and w > 1e-7: free.add(index)
        index += 1
    flat = attachment['triangles']; triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
    selected = [i for i, t in enumerate(triangles) if any(v in free for v in t)]
    if not selected: raise ValueError('cloth_strain_helper_empty')
    rows = []; reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('cloth_strain_reference_mismatch')
    for name, frames in reference['animations'].items():
        context = prepare(frames[0]['vertices'][slot], triangles)
        for frame in frames:
            low, high = stretches(frame['vertices'][slot], context)
            lo, hi = low[selected], high[selected]
            rows.append(dict(animation=name, time=frame['time'], min_stretch=float(np.min(lo)),
                             max_stretch=float(np.max(hi)),
                             max_anisotropy=float(np.max(hi/np.maximum(lo, 1e-12))),
                             passed=bool(np.all(lo >= .7) and np.all(hi <= 1.4))))
    return dict(schema='autospine.cloth-principal-strain/v1', authority='none', selected=False,
                profile='cloth-material-exploratory-070-140-v1', helper=helper,
                triangle_indices=selected, records=rows, passed=all(r['passed'] for r in rows),
                limits=dict(min_stretch=.7, max_stretch=1.4),
                limitation='exploratory_material_limits_not_visual_acceptance')
