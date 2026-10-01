"""Read-only draft trajectories on an already generated, source-bound mesh."""
import math
import re

from . import joint_wind
from .joint_spring import bake, interpolate, solve
from .joint_secondary_guard import _pose

GROUPS = ('hair', 'cloth', 'objects')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_template(template, report, document):
    if (template.get('schema') != 'autospine.wind-preview/v1'
            or any(template.get(k) != report.get(k) for k in
                   ('skeleton_sha256', 'parent_skeleton_sha256', 'config_sha256'))):
        raise ValueError('wind_preview_source_mismatch')
    ticks = template.get('times')
    if (not isinstance(ticks, list) or not 3 <= len(ticks) <= 14403 or ticks[0] != 0
            or any(not _number(t) for t in ticks)
            or abs(ticks[-1] - report['duration']) > 1e-9
            or not 0 < ticks[1] <= 1/60 + 1e-9
            or any(abs(b-a-ticks[1]) > 1e-8 for a,b in zip(ticks, ticks[1:]))):
        raise ValueError('wind_preview_samples_invalid')
    available = {b['name']: b for b in document['bones']}
    regions, bones, matrices = (template.get(k) for k in ('regions', 'bones', 'matrices'))
    if not isinstance(regions, list) or not 1 <= len(regions) <= 72 or not isinstance(bones, dict) or not isinstance(matrices, dict):
        raise ValueError('wind_preview_regions_invalid')
    owners, required, slots = set(), set(), set()
    for row in regions:
        if (not isinstance(row, dict) or row.get('region_kind') not in GROUPS
                or not isinstance(row.get('slot'), str) or row['slot'] in slots
                or not _number(row.get('post_solve_gain')) or not 0 <= row['post_solve_gain'] <= 1
                or not _number(row.get('wind_axis_offset')) or not isinstance(row.get('requested_config'), dict)
                or not isinstance(row.get('helpers'), list) or not 1 <= len(row['helpers']) <= 12):
            raise ValueError('wind_preview_regions_invalid')
        slots.add(row['slot'])
        for helper in row['helpers']:
            bone = bones.get(helper) if isinstance(helper, str) else None
            if (not isinstance(helper, str) or not re.match(r'^m5-(hair|response|object)-', helper)
                    or helper in owners or not bone or bone != available.get(helper)
                    or bone.get('parent') not in available):
                raise ValueError('wind_preview_helper_invalid')
            owners.add(helper); required.update((helper, bone['parent']))
    if set(bones) != owners or set(matrices) != required:
        raise ValueError('wind_preview_matrices_invalid')
    for rows in matrices.values():
        if (not isinstance(rows, list) or len(rows) != len(ticks)
                or any(not isinstance(m, list) or len(m) != 6 or any(not _number(v) for v in m) for m in rows)):
            raise ValueError('wind_preview_matrices_invalid')
    return template


def _chosen(config, slot):
    return config['enabled'] and (not config['slots'] or slot in config['slots'])


def _local(config, slot, key):
    return config['overrides'].get(slot, {}).get(key, config.get(key))


def _gain(record, report, config):
    gain = record['post_solve_gain']
    if (config['wind'].get('response_profile') == joint_wind.RESPONSE_PROFILE
            and report['config']['wind'].get('response_profile') != joint_wind.RESPONSE_PROFILE):
        history = next((r.get('history', []) for r in report['secondary'].get('geometry_guard', [])
                        if r['slot'] == record['slot']), [])
        measured = next((r for r in history if r.get('min_area_ratio', 0) >= .55
                         and r.get('max_area_ratio', 2) <= 1.9 and r.get('max_edge_stretch', 2) <= 1.9), None)
        if measured:
            gain = max(gain, measured['gain'])
    if not _number(gain) or not 0 <= gain <= 1:
        raise ValueError('wind_preview_gain_invalid')
    return gain


def compute(template, report, config, *, no_wind=False):
    ticks, regions, bones = (template[k] for k in ('times', 'regions', 'bones'))
    wind = dict(config['wind'], enabled=False if no_wind else config['wind']['enabled'])
    vectors, wind_report = joint_wind.vectors(wind, ticks, loop=config['loop'])
    frames = [{name: values[i] for name, values in template['matrices'].items()} for i in range(len(ticks))]
    tracks, pending, region_status = [], [], []
    def warn(message):
        if message not in pending: pending.append(message)
    for group in GROUPS:
        generated = {r['slot'] for r in regions if r['region_kind'] == group}
        for row in report['inventory'].get(group, []):
            if row['state'] == 'available' and _chosen(config[group], row['slot']) and row['slot'] not in generated:
                warn((row.get('name') or row['slot'])+'需先生成受风骨骼')
    for key, label in (('face', '表情改动'), ('fps', '采样率'), ('seed', '表情随机种子')):
        if report['config'][key] != config[key]: warn(label)
    for record in regions:
        kind, slot = record['region_kind'], record['slot']; cfg = config[kind]; solved = {}
        if kind == 'cloth' and cfg.get('response_profile', 'helper-local-v1') != record['requested_config'].get('response_profile', 'helper-local-v1'):
            warn(slot+'固定边缘过渡已改变，需重建后查看')
        for key in ('root_fraction', 'anchor_x', 'anchor_y'):
            if _local(cfg, slot, key) != record['requested_config'].get(key): warn(slot+'固定根部或挂点')
        gain = _gain(record, report, config) if _chosen(cfg, slot) else 0.
        for helper in record['helpers']:
            bone = bones[helper]; driven = bone['parent'] if kind == 'cloth' else helper
            carriers = frames
            if kind == 'hair' and cfg['cascade'] and solved:
                carriers = [_pose(frame, bones, record['helpers'], {n: solved[n][i] if n in solved else 0.
                            for n in record['helpers']}) for i,frame in enumerate(frames)]
            poses = [(p[driven][4], p[driven][5], math.degrees(math.atan2(p[driven][2], p[driven][0]))) for p in carriers]
            length = bone.get('length', 100.)
            external = joint_wind.angular_forces(vectors, poses, axis_offset=record['wind_axis_offset'],
                response=_local(cfg, slot, 'wind_response') or 0., length=length,
                profile=wind.get('response_profile', 'legacy-angular-v1'),
                stiffness=_local(cfg, slot, 'stiffness'), max_angle=_local(cfg, slot, 'max_angle'))
            values, _ = solve(ticks, poses, stiffness=_local(cfg, slot, 'stiffness'), damping=_local(cfg, slot, 'damping'),
                strength=_local(cfg, slot, 'strength')*(.5 if helper.endswith(('-lower', '_lower')) else 1.),
                max_angle=_local(cfg, slot, 'max_angle'), length=length, loop=config['loop'],
                external_forces=external, external_loop_compatible=wind_report['loop_compatible'])
            times, values, _ = bake(ticks, values)
            solved[helper] = [interpolate(times, values, t) for t in ticks]
            tracks.append(dict(bone=helper, times=times, values=[v*gain for v in values]))
        guard = next((r for r in report['secondary'].get('geometry_guard', []) if r['slot'] == slot), {})
        measured = (guard.get('history') or [{}])[-1]
        region_status.append(dict(slot=slot, kind=kind, gain=gain,
            built_projected_overlap=guard.get('collision', {}).get('policy') == 'diagnostic' and measured.get('collision_failed_samples', 0) > 0))
    changed = no_wind or any(report['config'].get(k) != config.get(k) for k in ('wind', *GROUPS, 'loop'))
    if changed: warn('新参数的网格、接触与 Runtime 验证')
    if config['loop'] and not wind_report['loop_compatible']: warn('风场首尾方向或强度不连续')
    return dict(tracks=tracks, changed=changed, pending=pending, regions=region_status,
        available=bool(tracks), mode='wind_solver', no_wind=no_wind, initial_from_rest=not config['loop'],
        reason='' if tracks else '当前候选没有可用的受风骨骼。')
