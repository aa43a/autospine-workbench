"""Compile explicit world-space pose edits into additive weighted deform.

No shape is inferred here. Authored points are candidate inputs, not ground truth.
Topology/UV stay fixed; seams, silhouettes and unsampled times need validation.
"""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256
from ...asset.planning.component_local_solver import metrics
from .affine_pose import sample, matrices
from .deform_addition import entries, local_delta, add


def _times(value):
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'time':
                if type(child) not in (int, float) or not math.isfinite(child) or child < 0:
                    raise ValueError('pose_patch_source_time_invalid')
                result.append(child)
            else:
                result.extend(_times(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_times(child))
    return result


def compile_patch(document, request):
    fields = {'document_sha256', 'mesh_sha256', 'animation', 'slot', 'vertices', 'interval', 'poses'}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError('pose_patch_request_invalid')
    if request['document_sha256'] != canonical_sha256(document):
        raise ValueError('pose_patch_document_changed')
    name, slot = request['animation'], request['slot']
    motion = document['animations'][name]
    if motion.get('deform'):
        raise ValueError('pose_patch_legacy_deform_unsupported')
    if any(k.get('curve') not in (None, 'stepped') for channels in motion.get('bones', {}).values()
           for keys in channels.values() for k in keys):
        raise ValueError('pose_patch_bezier_bone_timeline_unsupported')
    mesh = document['skins'][0]['attachments'][slot][slot]
    if request['mesh_sha256'] != canonical_sha256(mesh):
        raise ValueError('pose_patch_mesh_changed')
    influences = entries(mesh)
    selected = request['vertices']
    if (not isinstance(selected, list) or not 1 <= len(selected) <= 10000 or
            any(type(v) is not int or not 0 <= v < len(influences) for v in selected) or
            len(set(selected)) != len(selected)):
        raise ValueError('pose_patch_vertices_invalid')
    times = _times(motion)
    if len(set(times)) > 1536:
        raise ValueError('pose_patch_source_sample_budget')
    duration = max(times, default=0)
    interval = request['interval']
    if (not isinstance(interval, list) or len(interval) != 2 or
            any(type(t) not in (int, float) or not math.isfinite(t) for t in interval) or
            not 0 <= interval[0] < interval[1] <= duration):
        raise ValueError('pose_patch_interval_invalid')
    poses = request['poses']
    if not isinstance(poses, list) or not 1 <= len(poses) <= 512:
        raise ValueError('pose_patch_poses_invalid')
    previous = interval[0]
    for pose in poses:
        if (not isinstance(pose, dict) or set(pose) != {'time', 'points'} or
                type(pose['time']) not in (int, float) or not math.isfinite(pose['time']) or
                not previous < pose['time'] < interval[1]):
            raise ValueError('pose_patch_pose_time_invalid')
        points = pose['points']
        if (not isinstance(points, list) or len(points) != len(selected) or
                any(not isinstance(p, list) or len(p) != 2 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points)):
            raise ValueError('pose_patch_points_invalid')
        previous = pose['time']
    size = 2*sum(len(row) for row in influences)
    source_keys = motion.get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
    # The independent evaluator supports dense, linear keys starting at zero.
    if source_keys and (source_keys[0].get('time') != 0 or any(
            set(k) != {'time', 'vertices'} or len(k['vertices']) != size for k in source_keys)):
        raise ValueError('pose_patch_dense_linear_deform_required')
    corrections = {t: [0.]*size for t in (0, *interval, duration)}
    for pose in poses:
        t = pose['time']
        original = sample(document, name, t)[0][slot]
        corrected = deepcopy(original)
        for index, point in zip(selected, pose['points']):
            corrected[index] = point
        corrections[t] = local_delta(document, influences, matrices(document, name, t), original, corrected)
    result = deepcopy(document)
    target = result['animations'][name].setdefault('attachments', {}).setdefault('default', {}).setdefault(slot, {}).setdefault(slot, {})
    target['deform'] = add(source_keys, [dict(time=t, vertices=v) for t, v in sorted(corrections.items())], size)
    knots = sorted(set(times) | set(corrections))
    checked = sorted(set(knots) | {(a+b)/2 for a, b in zip(knots, knots[1:])})
    if len(checked) > 4097:
        raise ValueError('pose_patch_sample_budget')
    rest = sample(dict(document, animations={'setup': {}}), 'setup', 0)[0][slot]
    flat = mesh['triangles']
    triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
    records, unchanged_error, outside_error, authored_error = [], 0., 0., 0.
    selected_set = set(selected)
    for t in checked:
        before = sample(document, name, t)[0][slot]
        after = sample(result, name, t)[0][slot]
        unchanged_error = max(unchanged_error, max((math.dist(a, b) for i, (a, b) in
                              enumerate(zip(before, after)) if i not in selected_set), default=0))
        if t <= interval[0] or t >= interval[1]:
            outside_error = max(outside_error, max(math.dist(a, b) for a, b in zip(before, after)))
        records.append(dict(time=t, before=metrics(rest, before, triangles), after=metrics(rest, after, triangles)))
    for pose in poses:
        after = sample(result, name, pose['time'])[0][slot]
        authored_error = max(authored_error, max(math.dist(after[i], p) for i, p in zip(selected, pose['points'])))
    if max(unchanged_error, outside_error, authored_error) > 1e-6:
        raise ValueError('pose_patch_fidelity_failed')
    passed = all(not r['after']['bad_triangles'] and r['after']['max_edge_stretch'] <= 2 for r in records)
    return result, dict(profile='explicit-pose-geometry-patch-v1-experiment', authority='none', selected=False,
        request_sha256=canonical_sha256(request), input_sha256=request['document_sha256'],
        output_sha256=canonical_sha256(result), slot=slot, interval=interval, vertices=selected,
        sampled_geometry_passed=passed, records=records, authored_point_error_px=authored_error,
        unchanged_vertex_error_px=unchanged_error, outside_interval_error_px=outside_error,
        limitations=['explicit_points_are_not_visual_ground_truth', 'same_topology_and_uv_not_remeshing',
                     'interpolation_in_bone_local_offsets_not_world_linear',
                     'seams_silhouette_dense_runtime_and_other_regions_require_validation'])
