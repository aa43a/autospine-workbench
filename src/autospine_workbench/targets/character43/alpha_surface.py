"""A target-owned front surface hypothesis; never inferred anatomical geometry."""
import numpy as np
from scipy.ndimage import distance_transform_edt, map_coordinates


def build(points, uvs, triangles, alpha, depth_ratio=.25):
    points, uv = np.asarray(points, float), np.asarray(uvs, float)
    tri, alpha = np.asarray(triangles), np.asarray(alpha)
    if (points.ndim != 2 or points.shape[1] != 2 or uv.shape != points.shape or
            len(points) < 3 or not np.isfinite(points).all() or not np.isfinite(uv).all() or
            (uv < 0).any() or (uv > 1).any() or alpha.ndim != 2 or not alpha.size or
            not np.isfinite(alpha).all() or (alpha < 0).any() or (alpha > 255).any() or
            tri.ndim != 2 or tri.shape[1] != 3 or not tri.size or
            not np.issubdtype(tri.dtype, np.integer) or tri.min() < 0 or tri.max() >= len(points) or
            not np.isfinite(depth_ratio) or not 0 < depth_ratio <= 1):
        raise ValueError('alpha_surface_input')
    pixels = uv*np.array([alpha.shape[1], alpha.shape[0]])
    design = np.column_stack((pixels, np.ones(len(uv))))
    affine, _, rank, _ = np.linalg.lstsq(design, points, rcond=None)
    error = float(np.max(np.linalg.norm(design@affine-points, axis=1)))
    scales = np.linalg.svd(affine[:2], compute_uv=False)
    if rank < 3 or scales[-1] <= 1e-10 or error > 1e-4 or scales[0]/scales[-1] > 1.0001:
        raise ValueError('alpha_surface_requires_setup_similarity')
    # Pixel centers are at .5; padding makes even an opaque texture have a boundary.
    field = distance_transform_edt(np.pad(alpha >= 8, 1))
    distance = map_coordinates(field, [pixels[:, 1]+.5, pixels[:, 0]+.5],
                               order=1, mode='constant', cval=0.)
    x = np.minimum(np.floor(pixels[:, 0]).astype(int), alpha.shape[1]-1)
    y = np.minimum(np.floor(pixels[:, 1]).astype(int), alpha.shape[0]-1)
    distance[alpha[y, x] < 8] = 0
    depth = distance*float(scales.mean())*depth_ratio
    return dict(profile='alpha-front-surface-hypothesis-v1',
                vertices=np.column_stack((points, depth)).tolist(), uvs=uv.tolist(),
                triangles=tri.tolist(), pixel_to_world=float(scales.mean()),
                setup_affine_residual=error, depth_ratio=depth_ratio,
                maximum_depth=float(depth.max()), accepted=False, authority='none',
                limitations=['depth_is_assumed_not_reconstructed', 'front_surface_only',
                             'no_side_or_back_material', 'no_pose_or_visibility_validation'])
