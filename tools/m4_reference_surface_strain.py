"""Blender-only measured surface strain versus projection; no target gate changes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from autospine_workbench.targets.character43.surface_projection_evidence import inspect


def run(reference, output):
    report_raw = reference.read_bytes(); reference_data = json.loads(report_raw)
    sources = reference_data['sources']
    paths = {digest: Path(path) for path, digest in sources.items()}
    motion = paths[reference_data['motion_sha256']]
    model = paths[reference_data['model_sha256']]
    for digest, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('surface_source_changed')
    spec = importlib.util.spec_from_file_location('reference_render', Path(__file__).with_name('render-motion-surface-reference.py'))
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    times = sorted({r['time'] for r in reference_data['captures']})
    rest_bones, samples, source_world, clock = helper.capture_source(motion, times)
    rig = helper.load(model)
    if max(abs(a-b) for r, s in zip(source_world, rig.matrix_world) for a, b in zip(r, s)) > 1e-7:
        raise ValueError('surface_object_frame_changed')
    rig.animation_data_clear()
    meshes = [o for o in bpy.data.objects if o.type=='MESH']
    if not meshes or any(not any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers) for o in meshes):
        raise ValueError('surface_reference_skin_missing')
    for obj in meshes:
        obj.animation_data_clear()
    rig.data.pose_position = 'REST'; bpy.context.view_layer.update()
    parts = []
    for obj in meshes:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh = evaluated.to_mesh()
        if len(mesh.vertices) != len(obj.data.vertices):
            raise ValueError('surface_vertex_correspondence_changed')
        mesh.calc_loop_triangles()
        points = np.array([list(evaluated.matrix_world@v.co) for v in mesh.vertices])
        for side in ('Left', 'Right'):
            groups = {g.index for g in obj.vertex_groups if helper.name(g.name) in {side+'UpLeg', side+'Leg'}}
            weights = [sum(g.weight for g in v.groups if g.group in groups) for v in obj.data.vertices]
            triangles = [list(t.vertices) for t in mesh.loop_triangles if all(weights[v] >= .8 for v in t.vertices)]
            if not triangles:
                continue
            ids = sorted({i for t in triangles for i in t}); index = {v: i for i, v in enumerate(ids)}
            parts.append(dict(object=obj.name, side=side, vertex_ids=ids,
                              rest=points[ids].tolist(), triangles=[[index[i] for i in t] for t in triangles],
                              vertex_count=len(points)))
        evaluated.to_mesh_clear()
    if {p['side'] for p in parts} != {'Left', 'Right'}:
        raise ValueError('surface_bilateral_region_missing')
    rig.data.pose_position = 'POSE'; bpy.context.view_layer.update()
    records = []; endpoint_maximum = 0.
    for sample in samples:
        errors = helper.assign(rig, rest_bones, sample)
        endpoint_maximum = max(endpoint_maximum, max(max(e['head_error'], e['tail_error']) for e in errors))
        if endpoint_maximum >= 1e-5:
            raise ValueError('surface_source_endpoint_mismatch')
        for part in parts:
            obj = bpy.data.objects[part['object']]
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh = evaluated.to_mesh()
            if len(mesh.vertices) != part['vertex_count']:
                raise ValueError('surface_pose_topology_changed')
            points = [list(evaluated.matrix_world@mesh.vertices[i].co) for i in part['vertex_ids']]
            evaluated.to_mesh_clear()
            for capture in reference_data['captures']:
                if capture['time'] != sample['time']:
                    continue
                axes = np.array(capture['camera_world_matrix'])[:3, :3].T
                measured = inspect(part['rest'], points, part['triangles'], axes)
                # Orthographic ray to each triangle centroid. This is sampled
                # exposure, not a claim that the entire triangle is visible.
                distance = float(capture['ortho_scale'])*10
                direction = Vector((-axes[2]).tolist())
                deps = bpy.context.evaluated_depsgraph_get()
                for row, indices in zip(measured['triangles'], part['triangles']):
                    center = Vector(np.mean(np.asarray(points)[indices], axis=0).tolist())
                    origin = center-direction*distance
                    hit, location, _, _, hit_object, _ = bpy.context.scene.ray_cast(
                        deps, origin, direction, distance=distance*2)
                    row['centroid_exposed'] = bool(hit and hit_object.original.name==part['object'] and
                                                  (location-center).length < 1e-5)
                records.append(dict(time=sample['time'], object=part['object'], side=part['side'],
                                    yaw_degrees=capture['yaw_degrees'], camera_axes=axes.tolist(), posed=points,
                                    evidence=measured))
        print(json.dumps(dict(stage='measured', time=sample['time'])), flush=True)
    for digest, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('surface_source_changed_during_probe')
    output.mkdir(parents=True, exist_ok=False)
    result = dict(profile='source-reference-surface-strain-v1', authority='none', accepted=False,
                  reference_report_sha256=hashlib.sha256(report_raw).hexdigest(), sources=sources,
                  maximum_source_endpoint_error=endpoint_maximum, parts=parts, records=records,
                  limitations=['reference_body_not_target_artwork_or_mesh', 'does_not_waive_target_failures',
                               'three_diagnostic_poses_not_continuous_animation', 'no_new_render_capture',
                               'centroid_ray_visibility_is_not_full_triangle_or_pixel_visibility'])
    (output/'report.json').write_text(json.dumps(result), encoding='utf-8')
    summaries = []
    for r in records:
        rows = r['evidence']['triangles']
        summaries.append(dict(time=r['time'], object=r['object'], side=r['side'], triangles=len(rows),
            intrinsic_failed=sum(not t.get('intrinsic_gate_passed', False) for t in rows),
            screen_area_only=sum(t.get('projected_area_failure_with_intrinsic_pass', False) for t in rows),
            exposed_centroids=sum(t['centroid_exposed'] for t in rows),
            exposed_screen_area_only=sum(t['centroid_exposed'] and t.get('projected_area_failure_with_intrinsic_pass', False) for t in rows),
            winding_changed=sum(t.get('projected_winding_changed', False) for t in rows)))
    (output/'summary.json').write_text(json.dumps(summaries, indent=2), encoding='utf-8')
    print(json.dumps(summaries))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    run(args.reference, args.output)
