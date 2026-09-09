"""Local corrective pose experiments with source-bound replay."""
import math
from .component_local_solver import solve, ITERATIONS
from .component_mesh_tracks import _poses
from ...resolved_project import canonical_sha256


def build(source, skeleton):
    if (source['schema'] not in ('autospine.component-weight-transition/v1','autospine.component-parent-distal/v1')
            or source['skeleton_sha256'] != canonical_sha256(skeleton)
            or source['authority'] != 'none' or source['production_authorized'] is not False):
        raise ValueError('component_correction_source_mismatch')
    bones = {b['id']:b for b in skeleton['bones']}
    rows = []
    for row in source['records']:
        mesh = row['mesh']
        if not mesh or not mesh['qa'] or len(mesh['bone_ids']) != 3: continue
        poses = []
        for pose in _poses(mesh,skeleton):
            name, angle = pose['id'].rsplit('_',1)
            joint = mesh['bone_ids'].index(name)
            budget = .1*min(math.dist(bones[b]['head_xy'],bones[b]['tail_xy']) for b in mesh['bone_ids'])
            result = solve(mesh,pose['points'],joint,budget)
            poses.append(dict(id=pose['id'], **result))
        rows.append(dict(layer_id=row['layer_id'], component_id=row['component_id'], poses=poses))
    return dict(schema='autospine.component-local-correction/v1',profile='component-local-area-ring-v1',
                source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),
                project_id=source['project_id'],iterations=ITERATIONS,rows=rows,
                authority='none',production_authorized=False,seam_status='not_evaluated',runtime_status='not_evaluated',
                temporal_status='independent_probe_poses_only')
