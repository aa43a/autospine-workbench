"""Explicit wrist-anchored sleeve plane candidate, not observed cloth depth."""
import math

from .affine_pose import matrices

PROFILE = 'wrist-forearm-screen-vertical-cloth-plane-v1-experiment'


def fit(elbow, wrist, depths):
    """Fit depth along the forearm with zero screen-vertical depth gradient.

    This assumes cloth hangs in the plane spanned by the forearm and the screen
    vertical. It cannot recover real cloth thickness, folding or axial rotation.
    A nearly vertical projected forearm does not determine this plane.
    """
    if len(elbow)!=2 or len(wrist)!=2 or len(depths)!=2:
        raise ValueError('sleeve_plane_anchor_shape')
    if not all(math.isfinite(v) for v in (*elbow,*wrist,*depths)):
        raise ValueError('sleeve_plane_nonfinite')
    dx,dy=wrist[0]-elbow[0],wrist[1]-elbow[1]
    length=math.hypot(dx,dy)
    conditioning=abs(dx)/length if length>1e-8 else 0
    if conditioning<.1:
        raise ValueError('sleeve_plane_projected_axes_degenerate')
    slope=(depths[1]-depths[0])/dx
    return dict(profile=PROFILE,coefficients=[slope,0.,depths[1]-slope*wrist[0]],
        anchors=dict(elbow=dict(xy=list(elbow),depth=depths[0]),
                     wrist=dict(xy=list(wrist),depth=depths[1])),
        conditioning=conditioning,minimum_conditioning=.1,
        authority='none',selected=False,
        assumption='cloth_in_forearm_and_screen_vertical_plane_without_thickness',
        scope='explicit_planar_candidate_not_observed_or_accepted_cloth_depth')


def at(document,animation,time,sampler,source_tick,helper,parent):
    """Require an explicitly chosen helper attached at a mapped forearm wrist."""
    if parent not in ('forearm_l','forearm_r'):
        raise ValueError('sleeve_plane_forearm_required')
    bones={b['name']:b for b in document['bones']}
    bone=bones.get(helper);forearm=bones.get(parent);hand='hand_'+parent[-1]
    if bone is None or forearm is None or bone.get('parent')!=parent or hand not in bones:
        raise ValueError('sleeve_plane_helper_binding')
    length=forearm.get('length',0)
    if (length<=0 or abs(bone.get('x',0)-length)>1e-6 or abs(bone.get('y',0))>1e-6
            or bones[hand].get('parent')!=parent):
        raise ValueError('sleeve_plane_wrist_attachment_required')
    transforms=matrices(document,animation,time)
    elbow=list(transforms[parent][4:6]);wrist=list(transforms[hand][4:6])
    if math.dist(transforms[helper][4:6],wrist)>1e-6:
        raise ValueError('sleeve_plane_detached_helper')
    segments=sampler(source_tick)
    if parent not in segments:raise ValueError('sleeve_plane_source_depth_missing')
    result=fit(elbow,wrist,segments[parent])
    result.update(helper=helper,parent=parent,time=time,source_tick=source_tick)
    return result
