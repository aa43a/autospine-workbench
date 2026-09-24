"""Separate measured 3D surface strain from orthographic screen compression.

Source surfaces cannot authorize a target mesh. Visibility here is orientation
only: self-occlusion, depth ordering, seams and artwork still need rendering.
"""
import numpy as np


def inspect(rest, posed, triangles, camera_axes):
    rest, posed = np.asarray(rest, float), np.asarray(posed, float)
    tri = np.asarray(triangles)
    axes = np.asarray(camera_axes, float)
    if (rest.ndim != 2 or rest.shape[1] != 3 or posed.shape != rest.shape or
            tri.ndim != 2 or tri.shape[1] != 3 or not len(tri) or
            not np.issubdtype(tri.dtype, np.integer) or tri.min() < 0 or tri.max() >= len(rest) or
            axes.shape != (3, 3) or not np.isfinite(rest).all() or not np.isfinite(posed).all() or
            not np.isfinite(axes).all() or not np.allclose(axes@axes.T, np.eye(3), atol=1e-6) or
            abs(np.linalg.det(axes)-1) > 1e-6):
        raise ValueError('surface_projection_input')
    a, b = rest[tri], posed[tri]
    normal_a = np.cross(a[:, 1]-a[:, 0], a[:, 2]-a[:, 0])
    normal_b = np.cross(b[:, 1]-b[:, 0], b[:, 2]-b[:, 0])
    areas_a, areas_b = np.linalg.norm(normal_a, axis=1), np.linalg.norm(normal_b, axis=1)
    rows = []
    for i in range(len(tri)):
        if areas_a[i] <= 1e-12 or areas_b[i] <= 1e-12:
            rows.append(dict(triangle=i, status='degenerate_surface', accepted=False))
            continue
        intrinsic = float(areas_b[i]/areas_a[i])
        edges_a = np.linalg.norm(a[i]-np.roll(a[i], 1, axis=0), axis=1)
        edges_b = np.linalg.norm(b[i]-np.roll(b[i], 1, axis=0), axis=1)
        stretch = float(np.max(edges_b/edges_a))
        cosine_a = float(normal_a[i]@axes[2]/areas_a[i])
        cosine_b = float(normal_b[i]@axes[2]/areas_b[i])
        ratio = None if abs(cosine_a) <= 1e-6 else intrinsic*cosine_b/cosine_a
        intrinsic_pass = .5 <= intrinsic <= 2 and stretch <= 2
        rows.append(dict(triangle=i, status='measured', intrinsic_area_ratio=intrinsic,
                         maximum_intrinsic_edge_stretch=stretch,
                         rest_facing_cosine=cosine_a, posed_facing_cosine=cosine_b,
                         projected_signed_area_ratio=ratio,
                         projected_area_failure_with_intrinsic_pass=bool(
                             intrinsic_pass and ratio is not None and not .5 <= abs(ratio) <= 2),
                         projected_winding_changed=bool(ratio is not None and ratio < 0),
                         surface_orientation='edge_on' if abs(cosine_b) <= 1e-6 else
                             'front' if cosine_b > 0 else 'back',
                         intrinsic_gate_passed=intrinsic_pass, accepted=False))
    return dict(profile='orthographic-surface-projection-evidence-v1', triangles=rows,
                authority='none', accepted=False,
                limitations=['requires_actual_corresponding_3d_surface_not_joint_depth_only',
                             'orientation_is_not_occlusion_visibility',
                             'does_not_waive_target_geometry_or_authorize_adoption'])
