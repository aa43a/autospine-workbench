"""Source preparation and diagnostic fallback for the optional worker torso bake."""
from .torso_projection_source import anchors,shapes
from .torso_projection_candidate import PROFILE,build
from .torso_projection_validation import contact_preservation


def prepare(bundle,request):
    if request.get('torso_projection_profile')!=PROFILE:raise ValueError('motion_torso_profile_unsupported')
    frames,ticks=anchors(bundle,request.get('projection',{}).get('yaw_degrees',0))
    report=shapes(frames,[t/1e6 for t in ticks])
    clip=request.get('clip')
    if clip:
        start,end=clip['start_frame'],clip['end_frame'];origin=ticks[start]/1e6
        report['records']=[dict(r,time=r['time']-origin) for r in report['records'][start:end+1]]
        report['source_clip']=clip
    return report


def apply(document,animation,source,times):
    candidate,receipt=build(document,animation,source)
    receipt['applied']=candidate is not None
    if candidate is None:return document,receipt,'motion_torso_projection_unsupported'
    check=contact_preservation(document,candidate,animation,times)
    receipt['contact_preservation']=check
    reason=None if check['status']=='sampled_paths_preserved' else 'motion_torso_contact_needs_review'
    return candidate,receipt,reason
