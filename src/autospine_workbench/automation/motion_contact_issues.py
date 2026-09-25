"""Reconcile only obsolete drift findings after an exact final contact check."""
from copy import deepcopy
from ..resolved_project import canonical_sha256

DRIFT = {'motion_inferred_contact_drift', 'motion_contact_drift_needs_changes'}


def reconcile(issues, contact, document):
    check=contact.get('final_timeline_check',{})
    if check.get('skeleton_sha256')!=canonical_sha256(document):
        raise ValueError('motion_contact_issue_final_identity')
    active=[];resolved=[]
    for issue in issues:
        if (contact.get('after',{}).get('passed') is True and issue.get('stage')=='contact'
                and issue.get('reason_code') in DRIFT):
            resolved.append(dict(deepcopy(issue),resolution='final_sampled_ankle_check_passed',
                                 evidence=deepcopy(check)))
        else:active.append(deepcopy(issue))
    return active,resolved
