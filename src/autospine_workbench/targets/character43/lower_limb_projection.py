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


def view_summary(vectors,yaw):
    rows=[];count=None
    for side in ('left','right'):
        upper,lower=[vectors[f'humanoid.leg.{part}.{side}'] for part in ('upper','lower')]
        if not upper or len(upper)!=len(lower) or count not in (None,len(upper)):
            raise ValueError('knee_view_samples_mismatch')
        count=len(upper)
        rows.extend(dict(frame=i,side=side,**measure(u,l,yaw=yaw)) for i,(u,l) in enumerate(zip(upper,lower)))
    measured=[r for r in rows if r['hidden_bend_deg'] is not None]
    worst=max(measured,key=lambda r:r['hidden_bend_deg']) if measured else None
    return dict(sample_count=len(rows),unmeasured_samples=len(rows)-len(measured),
        maximum_hidden_bend_deg=None if worst is None else worst['hidden_bend_deg'],
        worst=None if worst is None else {k:worst[k] for k in ('frame','side','bend_3d_deg','bend_projected_deg')},
        minimum_length_ratio=min(min(r['projected_length_ratios']) for r in rows),
        samples_losing_30_degrees=sum(r['hidden_bend_deg']>=30 for r in measured),
        scope='source_knee_readability_not_character_artwork_or_occlusion')
