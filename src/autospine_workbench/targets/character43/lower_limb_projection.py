"""Measure 3D knee bend hidden by a declared camera projection, without changing pose."""
import math
from .oblique_motion import project


def angle(a,b):
    length=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    if length<=1e-12:return None
    return math.degrees(math.acos(max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/length))))


def measure(upper,lower,*,yaw=0):
    if (not math.isfinite(yaw) or not -90<=yaw<=90 or
            any(len(v)!=3 or any(not math.isfinite(x) for x in v) for v in (upper,lower))):
        raise ValueError('lower_limb_projection_input')
    lengths=[math.sqrt(sum(x*x for x in v)) for v in (upper,lower)]
    if min(lengths)<=1e-10:raise ValueError('lower_limb_projection_zero_segment')
    u,l=project(upper,yaw),project(lower,yaw)
    ankle=[a+b for a,b in zip(u,l)];den=sum(x*x for x in ankle)
    parameter=None if den<=1e-12 else sum(a*b for a,b in zip(u,ankle))/den
    offset=None if parameter is None else [u[i]-parameter*ankle[i] for i in range(3)]
    bend=angle(u,l);projected=angle(u[:2],l[:2])
    return dict(knee=list(u),ankle=ankle,bend_3d_deg=bend,bend_projected_deg=projected,
        hidden_bend_deg=None if projected is None else max(0.,bend-projected),
        projected_length_ratios=[math.hypot(*v[:2])/length for v,length in zip((u,l),lengths)],
        knee_chord_parameter=parameter,knee_depth_from_chord=None if offset is None else offset[2],
        knee_depth_ratio=None if offset is None else offset[2]/sum(lengths),
        depth_positive='declared_camera_basis',scope='source_bend_not_garment_surface_or_draw_order')
