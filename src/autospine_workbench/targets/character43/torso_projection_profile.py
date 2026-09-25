"""Source preparation and diagnostic fallback for the optional worker torso bake."""
from .torso_projection_source import anchors,shapes,reference_shapes
from .torso_projection_candidate import PROFILE,build
from .torso_projection_validation import contact_preservation

REFERENCE_PROFILE = 'reference-torso-plane-compensated-deform-v1-experiment'


def prepare(bundle,request):
    profile=request.get('torso_projection_profile')
    if profile not in (PROFILE,REFERENCE_PROFILE):raise ValueError('motion_torso_profile_unsupported')
    frames,ticks=anchors(bundle,request.get('projection',{}).get('yaw_degrees',0))
    if profile==REFERENCE_PROFILE:
        reference,reference_ticks=anchors(bundle,0)
        if ticks!=reference_ticks:raise ValueError('motion_torso_reference_times_mismatch')
        report=reference_shapes(frames,[t/1e6 for t in ticks],reference[0])
        report.update(reference_source_yaw=0,
            reference_assumption='source_initial_zero_yaw_matches_front_artwork',
            source_bundle_sha256=bundle.bundle_sha256,source_motion_sha256=bundle.clip_sha256,
            yaw_degrees=request.get('projection',{}).get('yaw_degrees',0))
    else:
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
