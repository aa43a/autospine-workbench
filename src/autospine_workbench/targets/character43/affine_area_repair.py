"""Mixed-weight corrective bake using inverse affine transforms, preserving fixed vertices."""
from copy import deepcopy
import math
from ...asset.joints.distal_corrective import project
from ..spine43.continuous_pose import area
from .affine_pose import matrices, sample


def repair(document, name, *, samples=257, convergent=False, setup_vertices=None, projected_reference=False, extra_times=(), temporal=False, terminal_collar=False, progress=None, proximal_ring=False):
    if proximal_ring and not terminal_collar:raise ValueError('proximal_ring_requires_collar')
    if terminal_collar and not (convergent and projected_reference):
        raise ValueError('character_collar_projection_required')
    if temporal and not (convergent and projected_reference):
        raise ValueError('character_temporal_projection_required')
    animation = document['animations'][name]
    if animation.get('attachments'):
        raise ValueError('character_affine_repair_existing_deform')
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('character_affine_repair_sample_limit')
    key_times = {k['time'] for tracks in animation['bones'].values() for keys in tracks.values() for k in keys}
    duration = max(key_times)
    if len(extra_times) > 1025 or any(not math.isfinite(t) or not 0 <= t <= duration for t in extra_times):
        raise ValueError('character_affine_extra_times_invalid')
    times = sorted(key_times | set(extra_times) | {duration*i/(samples-1) for i in range(samples)})
    if progress:progress(dict(stage='sample_geometry',sample_count=len(times)))
    worlds = [sample(document, name, t)[0] for t in times]
    transforms = [matrices(document, name, t) for t in times]
    rest_transforms = None
    if projected_reference:
        if setup_vertices is None or not convergent:
            raise ValueError('character_projected_area_setup_required')
        rest = deepcopy(document); rest['animations'] = {name: {'bones': {}}}
        rest_transforms = matrices(rest, name, 0)
    result = deepcopy(document); rows = []; bones = document['bones']
    attachments=document['skins'][0]['attachments']
    for slot_index,(slot, choices) in enumerate(attachments.items()):
        if progress:progress(dict(stage='inspect_attachment',slot=slot,slot_index=slot_index,total_slots=len(attachments)))
        attachment = choices[slot]; flat = attachment['triangles']
        triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
        base = (setup_vertices if setup_vertices is not None else worlds[0])[slot]; areas = [area(base, t) for t in triangles]
        ratios = [area(w[slot], t)/a for w in worlds for t, a in zip(triangles, areas)]
        if not projected_reference and min(ratios) >= .5 and max(ratios) <= 2:
            continue
        data = attachment['vertices']; influences = []; i = 0
        while i < len(data):
            count = data[i]; i += 1; entries = []
            for _ in range(count):
                index, _, _, weight = data[i:i+4]; i += 4; entries.append((index, weight))
            if abs(sum(w for _, w in entries)-1) > 1e-6:
                raise ValueError('character_affine_repair_weights')
            influences.append(entries)
        frame_areas = [areas]*len(times)
        if projected_reference:
            from .projected_area_reference import reference
            frame_areas = [reference(areas, triangles, influences, bones, rest_transforms, t) for t in transforms]
            ratios = [area(w[slot], tri)/a for w, refs in zip(worlds, frame_areas) for tri,a in zip(triangles,refs)]
            if min(ratios) >= .5 and max(ratios) <= 2:
                continue
        free = [sum(w > 0 for _, w in entries) > 1 for entries in influences]
        collars=[]
        if terminal_collar:
            from .terminal_joint_collar import propose
            for side in ('l','r'):
                if 'foot_'+side not in rest_transforms:continue
                collar=propose(base,triangles,influences,bones,rest_transforms,'calf_'+side,'foot_'+side)
                if proximal_ring:
                    from .terminal_joint_collar import extend_proximal_ring
                    collar=extend_proximal_ring(collar,triangles,influences,bones)
                for vertex in collar['vertices']:free[vertex]=True
                if collar['vertices']:collars.append(collar)
        used = {bones[i]['name'] for entries in influences for i, w in entries if w > 0}
        lengths = [math.hypot(b['x'], b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
        if not lengths or min(lengths) <= 0:
            raise ValueError('character_affine_repair_chain_missing')
        budget = .1*min(lengths)
        edges = sorted({tuple(sorted((t[i], t[(i+1)%3]))) for t in triangles for i in range(3)})
        context = dict(row={'triangles': triangles}, areas=areas, edges=edges,
                       lengths=[math.dist(base[a], base[b]) for a, b in edges], free=free, budget=budget)
        keys = []; maximum = 0.; unresolved = []; solver_rows = []
        for frame_index,(time, world, transform, references) in enumerate(zip(times, worlds, transforms, frame_areas)):
            if progress and frame_index%16==0:
                progress(dict(stage='solve_attachment',slot=slot,frame_index=frame_index,sample_count=len(times),time=time))
            context['areas'] = references
            original = world[slot]
            if convergent:
                from .area_projection import project as project_v2
                initial = None
                if temporal and keys:
                    from .corrective_transport import transport
                    initial = transport(original, influences, keys[-1]['vertices'], bones, transform)
                corrected, solver = project_v2(context, original, **({'initial':initial} if temporal else {}))
                if terminal_collar and not solver['converged']:
                    from .local_area_constraints import refine
                    corrected,solver['local_constraints']=refine(context,original,corrected,**({'analytic':True} if proximal_ring else {}))
                solver_rows.append(dict(time=time, **solver))
            else:
                corrected = project(context, original)
            corrected_ratios = [area(corrected, t)/a for t, a in zip(triangles, references)]
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
        if terminal_collar:rows[-1]['terminal_collars']=collars
        if progress:progress(dict(stage='attachment_complete',slot=slot,sample_count=len(times),unresolved_samples=len(unresolved)))
    profile = 'affine-mixed-area-budget10-v2' if convergent else 'affine-mixed-area-budget10-v1'
    if projected_reference:
        profile = 'affine-mixed-projected-area-budget10-v1'
    if temporal:
        profile = 'transported-projected-area-budget10-v1'
    if terminal_collar:profile='terminal-collar-projected-area-budget10-v1'
    if proximal_ring:profile='proximal-ring-projected-area-budget10-v1-experiment'
    return result, dict(profile=profile, authority='none', selected=False,
                        records=rows, validation='dense_resampling_required')
