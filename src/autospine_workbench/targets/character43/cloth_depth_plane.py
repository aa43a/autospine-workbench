"""Explicit planar garment proxy anchored to observed source torso depths."""
import math
from .affine_pose import matrices

PROFILE = 'torso-anchored-planar-garment-depth-v1-experiment'


def fit(points, depths):
    names = ('upperarm_l', 'upperarm_r', 'pelvis')
    if not all(n in points and n in depths for n in names):
        raise ValueError('cloth_plane_anchors_missing')
    a,b,c = [points[n] for n in names]
    za,zb,zc = [depths[n] for n in names]
    if not all(math.isfinite(v) for p in (a,b,c) for v in p) or not all(math.isfinite(v) for v in (za,zb,zc)):
        raise ValueError('cloth_plane_nonfinite')
    ux,uy = b[0]-a[0],b[1]-a[1]; vx,vy = c[0]-a[0],c[1]-a[1]
    det = ux*vy-uy*vx
    span = max(math.dist(a,b),math.dist(a,c),math.dist(b,c))
    if span <= 0 or abs(det)/span**2 < .01:
        raise ValueError('cloth_plane_projected_anchors_degenerate')
    dx = ((zb-za)*vy-(zc-za)*uy)/det
    dy = (ux*(zc-za)-vx*(zb-za))/det
    return dict(profile=PROFILE, coefficients=[dx,dy,za-dx*a[0]-dy*a[1]],
                anchors={n:dict(xy=points[n],depth=depths[n]) for n in names},
                normalized_area=abs(det)/span**2, authority='none', selected=False,
                assumption='garment_remains_in_torso_plane_without_thickness_or_out_of_plane_cloth_motion',
                scope='candidate_depth_model_not_observed_garment_surface')


def at(document, animation, time, sampler, source_tick):
    transforms = matrices(document, animation, time)
    points = {n:list(transforms[n][4:6]) for n in ('upperarm_l','upperarm_r','pelvis') if n in transforms}
    return fit(points,sampler.torso_anchors(source_tick))
