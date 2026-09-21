"""Compensate differing source/target root pivots using observed hip-center motion."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256
from .affine_pose import matrices

PROFILE='observed-hip-center-root-v1'


def apply(document,name,centers,times,source_reference,target_reference):
    if (len(times)!=len(centers) or len(times)<2 or times[0]!=0
            or any(not math.isfinite(t) or t<0 for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))
            or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in centers)
            or not all(math.isfinite(v) and v>0 for v in (source_reference,target_reference))):
        raise ValueError('hip_center_samples_invalid')
    bones={b['name']:b for b in document['bones']}
    if bones.get('root',{}).get('parent') or not all(n in bones for n in ('root','thigh_l','thigh_r')):
        raise ValueError('hip_center_target_invalid')
    for side in ('l','r'):
        ancestor='thigh_'+side
        while ancestor and ancestor!='root':ancestor=bones[ancestor].get('parent')
        if ancestor!='root':raise ValueError('hip_center_root_ancestry')
    result=deepcopy(document)
    track=result['animations'][name].setdefault('bones',{}).setdefault('root',{})
    original=matrices(document,name,0)
    origin=tuple((original['thigh_l'][i]+original['thigh_r'][i])/2 for i in (4,5))
    # Zero only the root translation before measuring its pivot-induced displacement.
    track['translate']=[]
    ratio=target_reference/source_reference;rows=[];keys=[]
    for time,center in zip(times,centers):
        pose=matrices(result,name,time)
        actual=tuple((pose['thigh_l'][i]+pose['thigh_r'][i])/2 for i in (4,5))
        desired=(origin[0]+(center[0]-centers[0][0])*ratio,
                 origin[1]-(center[1]-centers[0][1])*ratio)
        shift=[a-b for a,b in zip(desired,actual)]
        keys.append(dict(time=time,x=shift[0],y=shift[1]))
        before=matrices(document,name,time)
        previous=tuple((before['thigh_l'][i]+before['thigh_r'][i])/2 for i in (4,5))
        rows.append(dict(time=time,target=list(desired),before=list(previous),
                         pivot_error_px=math.dist(previous,desired)))
    track['translate']=keys
    error=0.
    for row in rows:
        pose=matrices(result,name,row['time'])
        actual=tuple((pose['thigh_l'][i]+pose['thigh_r'][i])/2 for i in (4,5))
        error=max(error,math.dist(actual,row['target']))
    return result,dict(profile=PROFILE,authority='none',selected=False,records=rows,
        input_sha256=canonical_sha256(dict(document=document,name=name,centers=centers,times=times,
            source_reference=source_reference,target_reference=target_reference)),output_sha256=canonical_sha256(result),
        maximum_before_error_px=max(r['pivot_error_px'] for r in rows),maximum_after_error_px=error,
        limitations=['hip_center_delta_not_absolute_pose','leg_proportion_and_contact_need_separate_checks'])
