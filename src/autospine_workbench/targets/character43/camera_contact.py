"""Contact proxy measured against a moving camera, never a stationary screen pixel."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256
from ..spine43.continuous_pose import interpolate
from .affine_pose import matrices
from .source_ankle_targets import targets
from .camera_ankle_targets import PROFILE as OBSERVATION_PROFILE
from .contact_windows import for_motion
from .motion_contacts import schedule

PROFILE = 'continuous-camera-contact-proxy-v1'


def _frames(values, times, side):
    return [dict(time=t,vertices=p[side]) for t,p in zip(times,values)]


def analyze(document, name, motion, report, times, reference, *, sample_limit=4096):
    observation=report['camera_observation']
    if (observation.get('profile') != OBSERVATION_PROFILE or
            report.get('source_motion_sha256') != canonical_sha256(motion) or
            observation['times'][-1] != motion['duration_ticks']/motion['ticks_per_second'] or
            canonical_sha256({k:v for k,v in observation.items() if k!='observation_sha256'}) != observation.get('observation_sha256')):
        raise ValueError('camera_contact_observation_identity')
    source=deepcopy(motion)
    if 'hypothesis' in report:
        source['markers']=for_motion(motion,report['hypothesis'])
    trajectory=targets(observation,report['initial_ankles'],reference)
    predicted=[_frames([r['targets'] for r in trajectory],observation['times'],s) for s in (0,1)]
    frozen=[_frames(observation['frozen_camera_points'],observation['times'],s) for s in (0,1)]
    scale=reference/observation['source_reference_length'];limit=reference*.01
    checked=schedule(source,times,sample_limit=sample_limit);poses={t:matrices(document,name,t) for t in checked};rows=[]
    for marker in source['markers']:
        if marker['kind']!='contact':continue
        side={'leg.left':0,'leg.right':1}[marker['limb']];bone='foot_'+('l' if side==0 else 'r')
        start,end=(marker[k]/source['ticks_per_second'] for k in ('start_tick','end_tick'))
        anchor=interpolate(frozen[side],start,'vertices');samples=[]
        for t,pose in poses.items():
            if not start<=t<end:continue
            target=interpolate(predicted[side],t,'vertices');actual=pose[bone][4:6]
            source_drift=math.dist(anchor,interpolate(frozen[side],t,'vertices'))*scale
            error=math.dist(actual,target)
            samples.append(dict(time=t,x=actual[0],y=actual[1],source_drift_px=source_drift,
                tracking_error_px=error,drift_px=max(source_drift,error),
                horizontal_px=abs(actual[0]-target[0]),vertical_px=abs(actual[1]-target[1])))
        worst=max(samples,key=lambda s:s['drift_px']) if samples else None
        rows.append(dict(limb=marker['limb'],bone=bone,start=start,end=end,anchor=anchor,samples=samples,
            max_drift_px=worst['drift_px'] if worst else None,worst_time=worst['time'] if worst else None,
            passed=worst['drift_px']<=limit if worst else None))
    passed=False if any(r['passed'] is False for r in rows) else None if not rows or any(r['passed'] is None for r in rows) else True
    return dict(status='needs_changes' if passed is False else 'camera_contact_proxy_passed' if passed else
        'unavailable_no_labels' if not rows else 'insufficient_contact_samples',passed=passed,intervals=rows,
        max_drift_px=max((r['max_drift_px'] for r in rows if r['max_drift_px'] is not None),default=None),
        drift_limit_px=limit,samples=len(checked))


def build(document,name,motion,observation,times,reference,*,hypothesis=None):
    initial=matrices(document,name,0)
    report=dict(schema='autospine.external-motion-contact/v1',policy_id=PROFILE,authority='none',
        source_motion_sha256=canonical_sha256(motion),input_skeleton_sha256=canonical_sha256(document),
        initial_ankles=[list(initial['foot_'+s][4:6]) for s in ('l','r')],camera_observation=observation,
        enabled=False,selected=False,reason_codes=[],
        scope='source_3d_ankle_stationarity_and_camera_target_tracking_not_sole_or_floor')
    if hypothesis is not None:report['hypothesis']=hypothesis
    checked=analyze(document,name,motion,report,times,reference)
    report.update(before=checked,after=checked,status=checked['status'])
    return report


def recheck(document,name,motion,report,times,reference):
    # Final M5 references admit 4097 probes. Their midpoint/boundary expansion
    # needs a separate bounded FK budget; keep every probe and the same tolerances.
    if len(times) > 4097:
        raise ValueError('motion_final_contact_times_invalid')
    result=deepcopy(report);checked=analyze(document,name,motion,result,times,reference,sample_limit=16384)
    result.update(pre_final_after=result.get('after'),after=checked,status=checked['status'],
        final_timeline_check=dict(profile=PROFILE,skeleton_sha256=canonical_sha256(document),
            animation=name,times_sha256=canonical_sha256(times),samples=checked['samples'],authority='none',
            scope='sampled_camera_compensated_contact_proxy_not_sole_or_floor'))
    return result
