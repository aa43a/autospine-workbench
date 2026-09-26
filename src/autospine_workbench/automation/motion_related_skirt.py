"""Expose selected-pose garment hypotheses without granting order authority."""
import math
from ..resolved_project import canonical_sha256


def summary(audit,candidate,skeleton,identity,duration):
    if (audit.get('artifact_sha256')!=candidate or audit.get('skeleton_sha256')!=skeleton
            or audit.get('source_identity')!=identity):
        raise ValueError('motion_related_skirt_identity')
    if (audit.get('profile')!='leg-skirt-surface-envelope-probe-v1'
            or audit.get('authority')!='none' or audit.get('selected') is not False
            or audit.get('order_changed') is not False or audit.get('production_authorized') is not False
            or audit.get('all_frames_checked') is not False):
        raise ValueError('motion_related_skirt_scope')
    times=audit.get('times',[]);rows=audit.get('rows',[])
    if (not 1<=len(times)<=9 or len(rows)>288 or times!=sorted(set(times))
            or any(type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<=duration+1e-6 for t in times)):
        raise ValueError('motion_related_skirt_times')
    values=[]
    for row in rows:
        pair=row.get('pair',[]);time=row.get('time')
        if (time not in times or len(pair)!=2 or not all(isinstance(n,str) for n in pair)
                or row.get('status') not in ('no_overlap','uniform_front_proxy','uniform_back_proxy',
                                           'requires_partition_or_more_depth','unmeasured')):
            raise ValueError('motion_related_skirt_row')
        counts=row.get('counts',{})
        if any(k not in ('front','back','unknown','ambiguous') or type(v) is not int or v<0 for k,v in counts.items()):
            raise ValueError('motion_related_skirt_counts')
        values.append(dict(time=time,pair=pair,status=row['status'],counts=counts,
                           reason_code=row.get('reason_code')))
    return dict(audit_sha256=canonical_sha256(audit),poses=len(times),rows=values,
                status='requires_review',all_frames_checked=False,
                scope='hypothetical_garment_surface_not_observed_depth',order_changed=False)
