"""Mixed-weight corrective bake using inverse affine transforms, preserving fixed vertices."""
from copy import deepcopy
import math
from ...asset.joints.distal_corrective import project
from ..spine43.continuous_pose import area, interpolate
from .affine_pose import matrices, sample


def repair(document, name, *, samples=257, convergent=False, setup_vertices=None, projected_reference=False, extra_times=(), temporal=False, terminal_collar=False, progress=None, proximal_ring=False, preserve_area=False, repair_band=False, fixed_band=False, area_margins=None, dual_floor=False, additive=False):
    if type(additive) is not bool:raise ValueError('character_affine_additive_mode_invalid')
    if dual_floor and (not convergent or not projected_reference or preserve_area):
        raise ValueError('dual_area_repair_mode_invalid')
    if area_margins is not None and not fixed_band:raise ValueError('area_margins_require_fixed_band')
    if fixed_band and not repair_band:raise ValueError('fixed_band_requires_repair_band')
    if repair_band and not preserve_area:raise ValueError('repair_band_requires_preservation')
    if preserve_area and not (convergent and projected_reference):raise ValueError('area_preservation_requires_projection')
    if proximal_ring and not terminal_collar:raise ValueError('proximal_ring_requires_collar')
    if terminal_collar and not (convergent and projected_reference):
        raise ValueError('character_collar_projection_required')
    if temporal and not (convergent and projected_reference):
        raise ValueError('character_temporal_projection_required')
    animation = document['animations'][name]
    if animation.get('attachments') and not additive:
        raise ValueError('character_affine_repair_existing_deform')
    if additive and (animation.get('deform') or set(animation.get('attachments',{}))-{'default'}):
        raise ValueError('character_affine_additive_layout_unsupported')
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('character_affine_repair_sample_limit')
    key_times = {k['time'] for tracks in animation['bones'].values() for keys in tracks.values() for k in keys}
    prior = animation.get('attachments',{}).get('default',{}) if additive else {}
    for slot, choices in prior.items():
        if set(choices)!={slot} or set(choices[slot])-{'deform'}:
            raise ValueError('character_affine_additive_layout_unsupported')
        keys=choices[slot].get('deform',[])
        if any('curve' in k or 'offset' in k for k in keys):
            raise ValueError('character_affine_additive_dense_linear_required')
        key_times.update(k['time'] for k in keys)
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
            if not dual_floor and min(ratios) >= .5 and max(ratios) <= 2:
                continue
            if additive and dual_floor and min(ratios) >= .5 and max(ratios) <= 2:
                setup_ratios = [area(w[slot], tri)/a for w in worlds for tri, a in zip(triangles, areas)]
                if min(setup_ratios) >= .5 and max(setup_ratios) <= 2:
                    checked_edges = {tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)}
                    if all(math.dist(w[slot][a],w[slot][b]) <= 2*math.dist(base[a],base[b])
                           for w in worlds for a,b in checked_edges):
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
        if dual_floor:
            from .fixed_area_feasibility import inspect as fixed_check, FixedAreaInfeasible
            feasibility=fixed_check(slot,triangles,areas,free,times,[w[slot] for w in worlds],frame_areas)
            if feasibility['failures']:raise FixedAreaInfeasible(feasibility)
        used = {bones[i]['name'] for entries in influences for i, w in entries if w > 0}
        lengths = [math.hypot(b['x'], b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
        if not lengths or min(lengths) <= 0:
            raise ValueError('character_affine_repair_chain_missing')
        budget = .1*min(lengths)
        edges = sorted({tuple(sorted((t[i], t[(i+1)%3]))) for t in triangles for i in range(3)})
        context = dict(row={'triangles': triangles}, areas=areas, edges=edges,
                       lengths=[math.dist(base[a], base[b]) for a, b in edges], free=free, budget=budget)
        keys = []; maximum = 0.; unresolved = []; solver_rows = []; previous_delta = None
        if area_margins is not None and slot in area_margins:context['solver_margins']=area_margins[slot]
        footprint=None
        if fixed_band:
            from .fixed_repair_band import collect
            footprint=collect(worlds,slot,triangles,frame_areas,{v for c in collars for v in c['vertices']})
        for frame_index,(time, world, transform, references) in enumerate(zip(times, worlds, transforms, frame_areas)):
            if progress and frame_index%16==0:
                progress(dict(stage='solve_attachment',slot=slot,frame_index=frame_index,sample_count=len(times),time=time))
            context['areas'] = references
            original = world[slot]
            if preserve_area:
                from .area_preservation import from_pose
                context['minimum_ratios'] = from_pose(original, triangles, references)
                if fixed_band:
                    for i in footprint:context['minimum_ratios'][i]=.5
                elif repair_band:
                    from .area_preservation import outside_repair_band
                    support={v for c in collars for v in c['vertices']}
                    context['minimum_ratios'],_ = outside_repair_band(original,triangles,references,support_vertices=support)
            if dual_floor:
                from .dual_area_floor import floors
                context['minimum_ratios'] = floors(areas,references)
                context['area_floor_contract'] = 'raw-compression-preservation-v1-experiment'
            if convergent:
                from .area_projection import project as project_v2
                initial = None
                if temporal and previous_delta is not None:
                    from .corrective_transport import transport
                    initial = transport(original, influences, previous_delta, bones, transform)
                corrected, solver = project_v2(context, original, **({'initial':initial} if temporal else {}))
                if terminal_collar and not solver['converged']:
                    from .local_area_constraints import refine
                    corrected,solver['local_constraints']=refine(context,original,corrected,
                        **({'analytic':True} if proximal_ring or repair_band else {}),**({'expanded':True} if repair_band else {}))
                solver_rows.append(dict(time=time, **solver))
            else:
                corrected = project(context, original)
            corrected_ratios = [area(corrected, t)/a for t, a in zip(triangles, references)]
            preservation_failed = (preserve_area or dual_floor) and any(r<f-1e-7 for r,f in zip(corrected_ratios,context['minimum_ratios']))
            if min(corrected_ratios) < .5 or max(corrected_ratios) > 2 or preservation_failed:
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
            previous_delta = offsets
            if additive:
                old_keys=prior.get(slot,{}).get(slot,{}).get('deform',[])
                old=interpolate(old_keys,time,'vertices') if old_keys else [0.]*len(offsets)
                if len(old)!=len(offsets) or any(not math.isfinite(v) for v in old):
                    raise ValueError('character_affine_additive_deform_inventory')
                offsets=[a+b for a,b in zip(old,offsets)]
            keys.append(dict(time=time, vertices=offsets))
        result['animations'][name].setdefault('attachments', {}).setdefault('default', {})[slot] = {slot: {'deform': keys}}
        rows.append(dict(slot=slot, max_displacement_px=maximum, budget_px=budget,
                         fixed_vertices=sum(not v for v in free), sample_count=len(times),
                         unresolved_area_samples=unresolved,
                         area_status='needs_review' if unresolved else 'sampled_pass'))
        if convergent:
            rows[-1]['solver_samples'] = solver_rows
        if terminal_collar:rows[-1]['terminal_collars']=collars
        if fixed_band:rows[-1]['fixed_repair_band']=footprint
        if progress:progress(dict(stage='attachment_complete',slot=slot,sample_count=len(times),unresolved_samples=len(unresolved)))
    profile = 'affine-mixed-area-budget10-v2' if convergent else 'affine-mixed-area-budget10-v1'
    if projected_reference:
        profile = 'affine-mixed-projected-area-budget10-v1'
    if temporal:
        profile = 'transported-projected-area-budget10-v1'
    if terminal_collar:profile='terminal-collar-projected-area-budget10-v1'
    if proximal_ring:profile='proximal-ring-projected-area-budget10-v1-experiment'
    if preserve_area:profile='healthy-area-preservation-budget10-v1-experiment'
    if repair_band:profile='repair-band-area-preservation-budget10-v1-experiment'
    if fixed_band:profile='fixed-band-area-preservation-budget10-v1-experiment'
    if area_margins is not None:profile='margin-fixed-band-preservation-budget10-v1-experiment'
    if dual_floor:profile='dual-reference-area-budget10-v1-experiment'
    evidence = dict(profile=profile, authority='none', selected=False,
                    records=rows, validation='dense_resampling_required')
    if additive:evidence['composition']='additive_to_existing_local_deform'
    return result, evidence
