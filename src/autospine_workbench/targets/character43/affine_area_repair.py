"""Mixed-weight corrective bake using inverse affine transforms, preserving fixed vertices."""
from copy import deepcopy
import math
from ...asset.joints.distal_corrective import project
from ..spine43.continuous_pose import area
from .affine_pose import matrices, sample


def repair(document, name, *, samples=257, convergent=False, setup_vertices=None):
    animation = document['animations'][name]
    if animation.get('attachments'):
        raise ValueError('character_affine_repair_existing_deform')
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('character_affine_repair_sample_limit')
    key_times = {k['time'] for tracks in animation['bones'].values() for keys in tracks.values() for k in keys}
    duration = max(key_times)
    times = sorted(key_times | {duration*i/(samples-1) for i in range(samples)})
    worlds = [sample(document, name, t)[0] for t in times]
    transforms = [matrices(document, name, t) for t in times]
    result = deepcopy(document); rows = []; bones = document['bones']
    for slot, choices in document['skins'][0]['attachments'].items():
        attachment = choices[slot]; flat = attachment['triangles']
        triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
        base = (setup_vertices if setup_vertices is not None else worlds[0])[slot]; areas = [area(base, t) for t in triangles]
        ratios = [area(w[slot], t)/a for w in worlds for t, a in zip(triangles, areas)]
        if min(ratios) >= .5 and max(ratios) <= 2:
            continue
        data = attachment['vertices']; influences = []; i = 0
        while i < len(data):
            count = data[i]; i += 1; entries = []
            for _ in range(count):
                index, _, _, weight = data[i:i+4]; i += 4; entries.append((index, weight))
            if abs(sum(w for _, w in entries)-1) > 1e-6:
                raise ValueError('character_affine_repair_weights')
            influences.append(entries)
        free = [sum(w > 0 for _, w in entries) > 1 for entries in influences]
        used = {bones[i]['name'] for entries in influences for i, w in entries if w > 0}
        lengths = [math.hypot(b['x'], b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
        if not lengths or min(lengths) <= 0:
            raise ValueError('character_affine_repair_chain_missing')
        budget = .1*min(lengths)
        edges = sorted({tuple(sorted((t[i], t[(i+1)%3]))) for t in triangles for i in range(3)})
        context = dict(row={'triangles': triangles}, areas=areas, edges=edges,
                       lengths=[math.dist(base[a], base[b]) for a, b in edges], free=free, budget=budget)
        keys = []; maximum = 0.; unresolved = []; solver_rows = []
        for time, world, transform in zip(times, worlds, transforms):
            original = world[slot]
            if convergent:
                from .area_projection import project as project_v2
                corrected, solver = project_v2(context, original)
                solver_rows.append(dict(time=time, **solver))
            else:
                corrected = project(context, original)
            corrected_ratios = [area(corrected, t)/a for t, a in zip(triangles, areas)]
            if min(corrected_ratios) < .5 or max(corrected_ratios) > 2:
                unresolved.append(dict(time=time, min_area_ratio=min(corrected_ratios),
                                       max_area_ratio=max(corrected_ratios)))
            offsets = []
            for vertex, (a, b, entries) in enumerate(zip(original, corrected, influences)):
                distance = math.dist(a, b)
                if distance > budget+1e-7 or (not free[vertex] and distance > 1e-7):
                    raise ValueError('character_affine_repair_budget')
                maximum = max(maximum, distance)
                dx, dy = b[0]-a[0], b[1]-a[1]
                for bone, _ in entries:
                    aa, ab, ac, ad, _, _ = transform[bones[bone]['name']]
                    det = aa*ad-ab*ac
                    if abs(det) < 1e-10:
                        raise ValueError('character_affine_repair_singular')
                    offsets.extend(((ad*dx-ab*dy)/det, (aa*dy-ac*dx)/det))
            keys.append(dict(time=time, vertices=offsets))
        result['animations'][name].setdefault('attachments', {}).setdefault('default', {})[slot] = {slot: {'deform': keys}}
        rows.append(dict(slot=slot, max_displacement_px=maximum, budget_px=budget,
                         fixed_vertices=sum(not v for v in free), sample_count=len(times),
                         unresolved_area_samples=unresolved,
                         area_status='needs_review' if unresolved else 'sampled_pass'))
        if convergent:
            rows[-1]['solver_samples'] = solver_rows
    profile = 'affine-mixed-area-budget10-v2' if convergent else 'affine-mixed-area-budget10-v1'
    return result, dict(profile=profile, authority='none', selected=False,
                        records=rows, validation='dense_resampling_required')
