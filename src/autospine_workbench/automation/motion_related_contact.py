"""Candidate-bound supplemental bone-proxy checks; never visual admission."""
import math
from ..resolved_project import canonical_sha256


def summary(audit, candidate, skeleton, runtime, times):
    moving=audit.get('moving_ankles',{})
    contact=audit.get('contact',{})
    final=contact.get('final_timeline_check',{})
    if (audit.get('profile')!='corrective-contact-audit-v1'
            or audit.get('artifact_sha256')!=candidate
            or audit.get('runtime_report_sha256')!=canonical_sha256(runtime)
            or contact.get('artifact_sha256')!=candidate
            or moving.get('skeleton_sha256')!=skeleton
            or final.get('skeleton_sha256')!=skeleton
            or final.get('times_sha256')!=canonical_sha256(times)
            or final.get('animation')!='external-motion'
            or moving.get('samples')!=len(times) or final.get('samples')!=len(times)):
        raise ValueError('motion_related_contact_identity')
    if (audit.get('authority')!='none' or audit.get('selected') is not False
            or audit.get('production_authorized') is not False
            or contact.get('runtime_numeric_passed') is not True):
        raise ValueError('motion_related_contact_authority')
    after=contact.get('after',{})
    result={}
    for name,error,limit,passed in (
            ('moving_ankles',moving.get('worst',{}).get('error_px'),moving.get('limit_px'),moving.get('passed')),
            ('ankle_contact',after.get('max_drift_px'),after.get('drift_limit_px'),after.get('passed'))):
        if (any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (error,limit))
                or limit<=0 or type(passed) is not bool or passed!=(error<=limit)):
            raise ValueError('motion_related_contact_measurement')
        result[name]=dict(passed=passed,error_px=error,limit_px=limit)
    result.update(samples=len(times),audit_sha256=canonical_sha256(audit),
        scope='cpu_bone_proxy_only',inferred='hypothesis' in contact,
        remaining_checks=['mesh_sole_contact','depth','visual'])
    return result
