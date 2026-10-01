"""Versioned, opt-in hair and clothing response for one joint Spine animation."""
from copy import deepcopy
import json
import math
import re

from .affine_pose import matrices
from .deform_addition import value
from .joint_secondary_mesh import hair, cloth, remove_probe
from .joint_spring import bake, grid, solve
from .joint_follow import HAIR_NAMES, OBJECT_NAMES, semantic, rigid_driver, pendulum
from . import joint_wind
from . import joint_cloth_falloff


def defaults(*, wind=False):
    result = dict(hair=dict(enabled=False, strength=1., stiffness=36., damping=.85,
                         max_angle=3., root_fraction=.35, cascade=False, slots=[], overrides={}),
                cloth=dict(enabled=False, strength=1., stiffness=25., damping=.9,
                           max_angle=2., slots=[], overrides={}),
                objects=dict(enabled=False, strength=1., stiffness=25., damping=.9,
                             max_angle=2., anchor_x=.5, anchor_y=1., slots=[], overrides={}), loop=False)
    if wind:
        result['wind'] = joint_wind.defaults()
        for kind in ('hair', 'cloth', 'objects'): result[kind]['wind_response'] = 1.
    return result


def normalize(config, duration):
    grid(duration)
    if not isinstance(config, dict) or set(config)-{'hair', 'cloth', 'objects', 'loop', 'wind'}:
        raise ValueError('joint_secondary_config')
    result = defaults(wind='wind' in config)
    if 'wind' in config: result['wind'] = joint_wind.normalize(config['wind'], duration)
    if 'loop' in config:
        if type(config['loop']) is not bool: raise ValueError('joint_secondary_loop')
        result['loop'] = config['loop']
    ranges = dict(strength=(0., 2.), stiffness=(9., 100.), damping=(.3, 2.),
                  max_angle=(0., 10.), root_fraction=(.15, .75), anchor_x=(0., 1.), anchor_y=(0., 1.), wind_response=(0., 2.))
    for kind in ('hair', 'cloth', 'objects'):
        row = config.get(kind, {})
        optional = {'response_profile'} if kind == 'cloth' else set()
        if not isinstance(row, dict) or set(row)-set(result[kind])-optional: raise ValueError('joint_secondary_fields')
        for key, item in row.items():
            if key == 'response_profile':
                if item not in (joint_cloth_falloff.LEGACY, joint_cloth_falloff.PROFILE):
                    raise ValueError('joint_cloth_response_profile')
            elif key in ('enabled', 'cascade'):
                if type(item) is not bool: raise ValueError('joint_secondary_enabled')
            elif key == 'slots':
                if (not isinstance(item, list) or len(item) > 24
                        or any(not isinstance(v, str) or not 1 <= len(v) <= 160 for v in item)
                        or len(set(item)) != len(item)):
                    raise ValueError('joint_secondary_slots')
                item = sorted(item)
            elif key == 'overrides':
                fields = {'strength', 'stiffness', 'damping', 'max_angle'} | ({'root_fraction'} if kind == 'hair' else set())
                if 'wind' in config: fields.add('wind_response')
                if kind == 'objects': fields |= {'anchor_x', 'anchor_y'}
                if not isinstance(item, dict) or len(item) > 24:
                    raise ValueError('joint_secondary_overrides')
                normalized = {}
                for slot, values in item.items():
                    if (not isinstance(slot, str) or not 1 <= len(slot) <= 160 or not isinstance(values, dict)
                            or set(values)-fields): raise ValueError('joint_secondary_override_fields')
                    normalized[slot] = {}
                    for field, val in values.items():
                        if type(val) not in (int, float) or not math.isfinite(val) or not ranges[field][0] <= val <= ranges[field][1]:
                            raise ValueError('joint_secondary_parameter_'+field)
                        normalized[slot][field] = float(val)
                item = dict(sorted(normalized.items()))
            else:
                if type(item) not in (int, float) or not math.isfinite(item) or not ranges[key][0] <= item <= ranges[key][1]:
                    raise ValueError('joint_secondary_parameter_'+key)
                item = float(item)
            result[kind][key] = item
    return result


def inventory(files, document):
    manifest = json.loads(files.get('character-manifest.json', b'{}'))
    attachments = document['skins'][0]['attachments']; names = {b['name'] for b in document['bones']}
    hairs = []; clothes = {}; objects = []; limitations = []
    for layer in manifest.get('layers', []):
        meaning = semantic(layer.get('name', ''))
        if meaning not in HAIR_NAMES | OBJECT_NAMES: continue
        for region in layer.get('regions', []):
            slot = region['region_id']
            if slot not in attachments: continue
            attachment = attachments[slot].get(slot, {})
            if meaning in OBJECT_NAMES:
                reason = None; driver = None
                try:
                    if 'residual' in slot: raise ValueError('joint_follow_residual_preserved')
                    index, _ = rigid_driver(document, slot)
                    driver = document['bones'][index]['name']
                except ValueError as exc:
                    reason = str(exc)
                objects.append(dict(slot=slot, name=layer['name'], root_driver=driver,
                    state='available' if reason is None else 'unsupported', reason=reason,
                    anchor_policy='adjustable_parent_local_bbox_pivot', anchor_x=.5, anchor_y=1.))
                continue
            reason = None
            if 'head' not in names: reason = 'head_missing'
            elif set(attachments[slot]) != {slot}: reason = 'attachment_variants'
            elif any(a.get('attachments', {}).get('default', {}).get(slot) for a in document['animations'].values()): reason = 'existing_hair_deform'
            elif 'images/'+attachment.get('path', slot)+'.png' not in files: reason = 'source_image_missing'
            if reason is None:
                try:
                    index, _ = rigid_driver(document, slot)
                    if document['bones'][index]['name'] != 'head': reason = 'joint_hair_existing_parent_not_head'
                except ValueError as exc:
                    reason = str(exc)
            hairs.append(dict(slot=slot, name=layer['name'], state='available' if reason is None else 'unsupported',
                              reason=reason, root_driver='head', root_fraction=.35))
    for bone in document['bones']:
        name = bone['name']; slot = None
        match = re.fullmatch(r'(.+)-skirt_\d+_(upper|lower)', name)
        if match: slot = match[1]
        elif name.startswith('cloth-'): slot = name[6:]
        if slot not in attachments: continue
        row = clothes.setdefault(slot, dict(slot=slot, helpers=[], root_drivers=[], state='available',
                                            kind='skirt' if match else 'sleeve'))
        row['helpers'].append(name)
        if bone.get('parent') not in row['root_drivers']: row['root_drivers'].append(bone.get('parent'))
    if not hairs: limitations.append('no_semantic_hair_layers')
    if not clothes: limitations.append('no_existing_clothing_helpers')
    return dict(profile='joint-secondary-inventory-v2', hair=hairs, cloth=list(clothes.values()), objects=objects, limitations=limitations)


def _points(document, animation, time, slot, transforms=None):
    mesh = document['skins'][0]['attachments'][slot][slot]
    data = mesh['vertices']; pose = transforms if transforms is not None else matrices(document, animation, time)
    keys = document['animations'][animation].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
    count = i = 0
    while i < len(data): n = data[i]; i += 1+4*n; count += n
    offsets = value(keys, time, count*2) if keys else [0.]*(count*2)
    result = []; i = j = 0
    while i < len(data):
        n = data[i]; i += 1; x = y = 0.
        for _ in range(n):
            bone, lx, ly, weight = data[i:i+4]; i += 4
            lx += offsets[j]; ly += offsets[j+1]; j += 2
            a, b, c, d, tx, ty = pose[document['bones'][bone]['name']]
            x += weight*(tx+a*lx+b*ly); y += weight*(ty+c*lx+d*ly)
        result.append([x, y])
    return result


def _camera_moving(keys):
    if not keys: return False
    angles = [k.get('yaw', k.get('angle', k.get('value'))) for k in keys]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in angles):
        raise ValueError('joint_secondary_camera_keys')
    return max(angles)-min(angles) > 1e-9


def apply(files, document, animation, config, times, camera_keys=None):
    if animation not in document['animations'] or not times or len(times) > 30000:
        raise ValueError('joint_secondary_animation_or_times')
    if times[0] != 0 or any(type(t) not in (int, float) or not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('joint_secondary_times')
    config = normalize(config, times[-1]); output = deepcopy(document)
    report = dict(profile='root-pinned-offline-secondary-v1', config=config, regions=[], skipped=[],
                  original_deform_preserved=True, camera_policy='fixed-camera-required',
                  collision_scope='baseline_relative_planar_head_torso_capsules_not_surface_or_self_collision',
                  visual_acceptance='not_evaluated', root_error_px=0., probe_tracks_replaced=[])
    if not any(config[k]['enabled'] for k in ('hair', 'cloth', 'objects')):
        report['status'] = 'disabled'; return output, report
    if _camera_moving(camera_keys):
        report.update(status='blocked', skipped=[dict(reason='camera_inertia_requires_unprojected_body_driver')])
        return output, report
    if any(b['name'].startswith(('m5-hair-', 'm5-response-', 'm5-object-')) for b in document['bones']):
        raise ValueError('joint_secondary_already_applied')
    catalog = inventory(files, document); records = []; selected = set()
    for kind in ('hair', 'cloth', 'objects'):
        cfg = config[kind]
        if not cfg['enabled']: continue
        rows = catalog[kind]; requested = set(cfg['slots'])
        if requested-set(r['slot'] for r in rows): raise ValueError('joint_secondary_unknown_slot')
        if set(cfg['overrides'])-set(r['slot'] for r in rows): raise ValueError('joint_secondary_unknown_override_slot')
        for row in rows:
            slot = row['slot']
            if requested and slot not in requested: continue
            if row['state'] != 'available':
                report['skipped'].append(dict(slot=slot, reason=row['reason'])); continue
            try:
                trial = deepcopy(output)
                local_config = {k:v for k,v in cfg.items() if k not in ('enabled', 'slots', 'overrides')}
                local_config.update(cfg['overrides'].get(slot, {}))
                if kind == 'hair': record = hair(files, trial, slot, local_config['root_fraction'])
                elif kind == 'objects': record = pendulum(trial, slot, local_config['anchor_x'], local_config['anchor_y'])
                else: record = cloth(trial, slot, row['helpers'],
                    response_profile=local_config.get('response_profile', joint_cloth_falloff.LEGACY))
                record['requested_config'] = local_config
            except ValueError as exc:
                if not str(exc).startswith(('joint_', 'skirt_')): raise
                report['skipped'].append(dict(slot=slot, reason=str(exc))); continue
            output = trial; records.append(record); selected.add(slot)
            if kind == 'cloth':
                report['probe_tracks_replaced'].extend(remove_probe(output, animation, row['helpers']))
    # Sample all carriers from the same baseline before adding any response.
    # Parents inherit body/face and existing repaired cloth, never camera drag.
    baseline = deepcopy(output); ticks = grid(times[-1]); poses = [matrices(baseline, animation, t) for t in ticks]
    wind_values = None
    if 'wind' in config:
        wind_values, report['wind'] = joint_wind.vectors(config['wind'], ticks, loop=config['loop'])
    key_indices = sorted(set(range(0, len(ticks), 2)) | {len(ticks)-1})
    all_key_times = {ticks[i] for i in key_indices}
    indices = {b['name']: b for b in baseline['bones']}; tracks = output['animations'][animation].setdefault('bones', {})
    for record in records:
        kind = record['region_kind']; cfg = record['requested_config']; spring_reports = []
        solved = {}
        for helper in record['helpers']:
            driven = helper if kind in ('hair', 'objects') else indices[helper]['parent']
            # Recompute just the new hair chain, feeding its solved upstream motion
            # into the lower segment. Existing body and repaired cloth stay frozen.
            carrier_poses = poses
            if kind == 'hair' and cfg['cascade'] and solved:
                from .joint_secondary_guard import _pose
                carrier_poses = [_pose(p, indices, record['helpers'],
                    {n: solved[n][i] if n in solved else 0. for n in record['helpers']}) for i,p in enumerate(poses)]
            root_poses = [(p[driven][4], p[driven][5], math.degrees(math.atan2(p[driven][2], p[driven][0]))) for p in carrier_poses]
            external = None
            if wind_values is not None:
                external = joint_wind.angular_forces(wind_values, root_poses,
                    axis_offset=record.get('wind_axis_offset', 0.), response=cfg['wind_response'],
                    length=indices[helper].get('length', 100.),
                    profile=config['wind'].get('response_profile', 'legacy-angular-v1'),
                    stiffness=cfg['stiffness'], max_angle=cfg['max_angle'])
            response, evidence = solve(ticks, root_poses, stiffness=cfg['stiffness'], damping=cfg['damping'],
                strength=cfg['strength']*(.5 if helper.endswith('-lower') or helper.endswith('_lower') else 1.),
                max_angle=cfg['max_angle'], length=indices[helper].get('length', 100.), loop=config['loop'],
                external_forces=external, external_loop_compatible=not external or report['wind']['loop_compatible'])
            if external is not None:
                evidence['wind_peak_acceleration_deg_s2'] = max(map(abs, external))
                if config['loop'] and not report['wind']['loop_compatible']:
                    evidence['loop_status'] = 'wind_not_loopable'
            key_times, key_values, sampling = bake(ticks, response)
            from .joint_spring import interpolate
            solved[helper] = [interpolate(key_times, key_values, t) for t in ticks]
            all_key_times.update(key_times)
            evidence.update(solver_sample_count=len(ticks), driver_mode='cascaded_hair' if cfg.get('cascade') else 'baseline_parent', **sampling)
            tracks[helper] = {'rotate': [dict(time=t, value=v) for t, v in zip(key_times, key_values, strict=True)]}
            spring_reports.append(dict(helper=helper, **evidence))
        record['springs'] = spring_reports
        record['peak_response_deg'] = max((r['peak_angle_deg'] for r in spring_reports), default=0.)
        record['motion_status'] = 'responding' if record['peak_response_deg'] > 1e-6 else 'static_driver_no_inertia'
    from .joint_secondary_guard import protect
    overlap_policy = ('diagnostic' if config.get('wind', {}).get('response_profile') == joint_wind.RESPONSE_PROFILE else 'bounded')
    report['geometry_guard'] = protect(output, baseline, animation, records, ticks, poses, _points,
                                       projected_overlap=overlap_policy)
    if overlap_policy == 'diagnostic':
        report['collision_scope'] = 'projected_overlap_diagnostic_not_physical_collision'
    for record in records:
        record['effective_config'] = dict(record['requested_config'],
            strength=record['requested_config']['strength']*record['effective_gain'],
            max_angle=record['requested_config']['max_angle']*record['effective_gain'])
        record['post_solve_gain'] = record['effective_gain']
        if record['effective_gain'] == 0:
            report['skipped'].append(dict(slot=record['slot'], reason='new_response_suppressed_for_geometry'))
    if wind_values is not None and records:
        # Immutable carrier matrices let the browser solve a draft once and seek
        # it deterministically. Drafts do not reuse the old geometry verdict.
        names = sorted({n for r in records for h in r['helpers'] for n in (h, indices[h]['parent'])})
        report['preview_data'] = dict(schema='autospine.wind-preview/v1', times=ticks,
            bones={h: indices[h] for r in records for h in r['helpers']},
            matrices={n: [list(p[n]) for p in poses] for n in names},
            regions=[{k:r[k] for k in ('slot', 'region_kind', 'helpers', 'requested_config', 'post_solve_gain')}
                | {'wind_axis_offset':r.get('wind_axis_offset', 0.)} for r in records])
    # Fixed material roots must agree with the exact zero-response baseline.
    checks = sorted(set(times[::max(1, len(times)//32)]+[times[-1]]))
    for record in records:
        slot = record['slot']; root_error = 0.; displacement = 0.
        for t in checks:
            a = _points(baseline, animation, t, slot); b = _points(output, animation, t, slot)
            root_error = max(root_error, max((math.dist(a[i], b[i]) for i in record['pinned_vertices']), default=0.))
            displacement = max(displacement, max((math.dist(p, q) for p, q in zip(a, b, strict=True)), default=0.))
            if record.get('pivot_helper'):
                name = record['pivot_helper']
                p = matrices(baseline, animation, t)[name]; q = matrices(output, animation, t)[name]
                root_error = max(root_error, math.dist(p[4:6], q[4:6]))
        record['root_error_px'] = root_error; record['peak_sampled_displacement_px'] = displacement
        record.pop('expected_setup', None)
        report['root_error_px'] = max(report['root_error_px'], root_error)
    if report['root_error_px'] > 1e-7: raise ValueError('joint_secondary_root_changed')
    loop_issues = [dict(slot=r['slot'], helper=s['helper'], reason=s['loop_status'])
                   for r in records for s in r['springs']
                   if config['loop'] and s['loop_status'] != 'converged']
    if any(row['reason'] == 'not_converged' for row in loop_issues):
        report['skipped'].append(dict(reason='secondary_loop_not_converged'))
    report.update(regions=records, loop_issues=loop_issues,
        sample_count=len(ticks), solver_sample_count=len(ticks),
        key_sample_count=len(all_key_times), root_check_samples=len(checks),
        key_sampling='60hz_with_required_120hz_corners',
        enabled_slots=sorted(selected), affected_slots=sorted(selected), sample_times=sorted(all_key_times),
        status='applied' if records and not report['skipped'] else 'partial' if records else 'blocked',
        preserved=['body_bones', 'source_rgba', 'draw_order', 'source_animation_channels_except_identified_skirt_probe'],
        limitations=['planar_bounded_response', 'hair_root_band_is_adjustable_geometric_proposal',
                     'object_pivot_is_adjustable_geometric_proposal_not_semantic_mount',
                     'surface_occlusion_requires_joint_runtime_review'])
    return output, report
