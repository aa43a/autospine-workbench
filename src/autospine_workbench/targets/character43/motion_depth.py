"""Source-bound arm/torso depth candidates; no implicit draw-order adoption."""
from hashlib import sha256
import math

from ...bvh_fk import project_bvh_frames
from ...depth_order_schmitt import evaluate_depth_pair
from ...resolved_project import canonical_sha256

PROFILE = 'external-arm-torso-depth-review-v1'
OVERLAP_PROFILE = 'external-arm-torso-depth-overlap-v2'


def _source(bvh, mapping, kimodo, yaw_degrees=None, *, camera_keys=None,sampling_profile=None,sample_times=None):
    if camera_keys is not None and yaw_degrees is not None:
        raise ValueError('motion_depth_camera_conflict')
    angle=math.radians(yaw_degrees or 0); c,s=math.cos(angle),math.sin(angle)
    if kimodo is None:
        projected = project_bvh_frames(bvh, mapping)
        if camera_keys is not None:
            from .camera_depth import sample_rows
            rows=[(f.tick,{n:(p.screen_xy[0],p.depth) for n,p in f.joints}) for f in projected.frames]
            return sample_rows(rows,camera_keys,sampling_profile,**(dict(sample_times=sample_times) if sample_times is not None else {})), \
                mapping['root']['reference_length_source_units'], bvh.source_sha256
        return [(f.tick, {n: p.depth if yaw_degrees is None else s*p.screen_xy[0]+c*p.depth
                         for n, p in f.joints}) for f in projected.frames], \
            mapping['root']['reference_length_source_units'], bvh.source_sha256
    from ...kimodo_npz_reader import decode_kimodo_npz
    from ...kimodo_npz_consistency import validate_kimodo_consistency
    from ...kimodo_npz_map_validation import require_kimodo_npz_map
    from ...kimodo_npz_projection import kimodo_frame_ticks
    from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
    raw, source = kimodo
    require_kimodo_npz_map(mapping, source=source)
    validated = validate_kimodo_consistency(decode_kimodo_npz(raw, source), source)
    axis = mapping['basis']['depth']; index = 'XYZ'.index(axis[1]); sign = 1 if axis[0] == '+' else -1
    xaxis=mapping['basis']['screen_x']; xindex='XYZ'.index(xaxis[1]); xsign=1 if xaxis[0]=='+' else -1
    if camera_keys is not None:
        from .camera_depth import sample_rows
        ticks=kimodo_frame_ticks(source)
        rows=[(tick,{n:(xsign*positions[i][xindex],sign*positions[i][index])
                       for n,i in SOMA77_INDEX_BY_NAME.items()})
                for tick,positions in zip(ticks,validated.positions)]
        return sample_rows(rows,camera_keys,sampling_profile,**(dict(sample_times=sample_times) if sample_times is not None else {})), \
            mapping['root']['reference_length_meters'], sha256(raw).hexdigest()
    rows = [(tick, {n: sign*positions[i][index] if yaw_degrees is None else
                   s*xsign*positions[i][xindex]+c*sign*positions[i][index] for n, i in SOMA77_INDEX_BY_NAME.items()})
            for tick, positions in zip(kimodo_frame_ticks(source), validated.positions)]
    return rows, mapping['root']['reference_length_meters'], sha256(raw).hexdigest()


def _slots(document, *, render_regions=False):
    bones = document['bones']; parents = {b['name']: b.get('parent') for b in bones}
    def owner(name):
        original_name = name
        while name:
            if name in ('upperarm_l', 'forearm_l', 'hand_l'): return 'left'
            if name in ('upperarm_r', 'forearm_r', 'hand_r'): return 'right'
            if name in ('head', 'neck', 'thigh_l', 'thigh_r', 'calf_l', 'calf_r', 'foot_l', 'foot_r'):
                return 'other'
            if name == 'chest': return 'torso' if original_name == 'chest' else 'other'
            name = parents.get(name)
        return 'other'
    result = {key: [] for key in ('left', 'right', 'torso', 'other')}
    for slot in document['slots']:
        attachment = document['skins'][0]['attachments'][slot['name']][slot['attachment']]
        weights = attachment.get('vertices', [])
        if attachment.get('type') != 'mesh' or len(weights) == len(attachment.get('uvs', [])):
            owners = {owner(slot['bone'])}
        else:
            owners = set(); i = 0; vertex = 0
            used = set(attachment.get('triangles', [])) if render_regions else None
            while i < len(weights):
                count = weights[i]; i += 1
                for _ in range(count):
                    index, _, _, weight = weights[i:i+4]; i += 4
                    if (used is None or vertex in used) and weight > (0 if render_regions else 1e-8):
                        owners.add(owner(bones[index]['name']))
                vertex += 1
        group = next(iter(owners)) if len(owners) == 1 else 'other'
        result[group].append(slot['name'])
    return result


def build(document, bvh, mapping, *, kimodo=None, clip_bounds=None, yaw_degrees=None, render_regions=False,
          camera_keys=None,sampling_profile=None,sample_times=None):
    if yaw_degrees is not None:
        from .oblique_target import validate
        from .oblique_motion import PROFILE as OBLIQUE_PROFILE
        validate(dict(profile=OBLIQUE_PROFILE,yaw_degrees=yaw_degrees))
    if camera_keys is not None and yaw_degrees is not None:
        raise ValueError('motion_depth_camera_conflict')
    options = dict(camera_keys=camera_keys,sampling_profile=sampling_profile) if camera_keys is not None else {}
    if sample_times is not None:
        if camera_keys is None:raise ValueError('motion_depth_sampling_requires_camera')
        options['sample_times']=sample_times
    if sampling_profile is not None and camera_keys is None:raise ValueError('motion_depth_sampling_requires_camera')
    frames, length, source_sha = _source(bvh, mapping, kimodo, yaw_degrees, **options)
    roles = {r['role']: r for r in mapping['bones']}
    groups = _slots(document, render_regions=render_regions)
    report = dict(profile=PROFILE, authority='none', selected=False, source_sha256=source_sha,
        map_sha256=canonical_sha256(mapping), depth_axis=mapping['basis']['depth'],
        depth_positive='toward_camera', groups=groups, pairs=[],
        scope='source_depth_order_candidate_not_raster_occlusion_validation',
        limits=dict(enter_ratio=.04, exit_ratio=.02, minimum_hold_frames=3),
        limitations=['source_depth_does_not_prove_target_pixel_overlap',
                     'straddling_arm_requires_partition_or_review', 'unclassified_slots_keep_setup_order'])
    if render_regions:
        report.update(profile='external-render-region-depth-review-v1-experiment',
                      ownership_scope='all_positive_influences_of_rendered_triangle_vertices')
    hold={}
    if sampling_profile is not None:
        from ...bvh_fk import bvh_frame_ticks
        from ...kimodo_npz_projection import kimodo_frame_ticks
        native=kimodo_frame_ticks(kimodo[1]) if kimodo else bvh_frame_ticks(bvh)
        span=math.ceil(2*(native[-1]-native[0])/(len(native)-1))
        hold=dict(minimum_hold_ticks=max(1,span))
        report['limits'].update(minimum_hold_frames=1,minimum_hold_ticks=hold['minimum_hold_ticks'],
            hold_profile='two_native_frame_intervals_elapsed_v1',ticks_per_second=1_000_000)
    torso = roles.get('humanoid.spine.upper')
    if yaw_degrees is not None:
        report.update(projection_profile=OBLIQUE_PROFILE,yaw_degrees=yaw_degrees,
                      depth_axis='yaw_rotated_declared_basis')
    if camera_keys is not None:
        from .camera_depth import receipt
        camera = receipt(camera_keys, [tick for tick,_ in frames])
        if sampling_profile is not None:
            camera.update(sampling_profile=sampling_profile,sample_scope='interpolated_world_observations_not_native_frames')
        report.update(projection_profile=camera['profile'], camera=camera,
                      depth_axis='per_frame_yaw_rotated_declared_basis')
    if not torso or not groups['torso']:
        report['status'] = 'depth_mapping_unavailable'
        return report
    start, end = clip_bounds or (0, frames[-1][0])
    selected = [(i, tick, joints) for i, (tick, joints) in enumerate(frames) if start <= tick <= end]
    if not selected:
        raise ValueError('motion_depth_clip_empty')
    order = {s['name']: i for i, s in enumerate(document['slots'])}
    for side in ('left', 'right'):
        upper, lower = (roles.get('humanoid.arm.'+part+'.'+side) for part in ('upper', 'lower'))
        if not upper or not lower or not groups[side]:
            continue
        aim = lower.get('aim', {}).get('joint_name') or lower.get('aim_joint_name')
        if not aim:
            continue
        names = [upper['joint_name'], lower['joint_name'], aim]
        observations = []
        for index, tick, joints in selected:
            differences = [(joints[n]-joints[torso['joint_name']])/length for n in names]
            ambiguous = min(differences) < -.02 and max(differences) > .02
            observations.append(dict(source_frame_index=index, tick=tick-start,
                source_tick=tick, min_depth_ratio=min(differences), max_depth_ratio=max(differences),
                depth_ratio=sum(differences)/len(differences), ambiguous=ambiguous))
        for arm in groups[side]:
            for body in groups['torso']:
                pair = tuple(sorted((arm, body)))
                rows = [dict(source_frame_index=r['source_frame_index'], tick=r['tick'],
                    scores={arm: 0 if r['ambiguous'] else r['depth_ratio'], body: 0}) for r in observations]
                samples, events = evaluate_depth_pair(rows, slot_ids=pair,
                    setup_front_slot=max(pair, key=order.__getitem__), enter_threshold=.04,
                    exit_threshold=.02, minimum_hold_frames=1 if hold else 3,**hold)
                report['pairs'].append(dict(arm_slot=arm, torso_slot=body, side=side,
                    setup_front_slot=max(pair, key=order.__getitem__), events=events,
                    samples=[dict(o, **s) for o, s in zip(observations, samples)]))
    switches = sum(len(p['events']) for p in report['pairs'])
    ambiguous = sum(sum(s['ambiguous'] for s in p['samples']) for p in report['pairs'])
    report.update(switch_candidates=switches, ambiguous_pair_samples=ambiguous,
        status='depth_candidates_need_review' if switches or ambiguous else
               'depth_evidence_no_switch' if report['pairs'] else 'depth_mapping_unavailable')
    return report
