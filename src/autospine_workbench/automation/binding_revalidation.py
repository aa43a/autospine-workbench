"""Re-evaluate stale automatic selections without writing or changing decisions."""
from copy import deepcopy
from types import SimpleNamespace
from .head_parts_policy import propose

POLICIES={'compact-foot-binding-v1','head-foot-contact-binding-v3',
          'reviewed-head-anchor-binding-v4','head-and-foot-binding-v2','bounded-head-parts-binding-v5'}


def revalidate(source, rows):
    results=[]
    for row in rows:
        if row['decision_source']!='policy_auto' or row['evidence_current'] is True:
            continue
        result=dict(layer_id=row['layer_id'],decision_sha256=row['decision_sha256'],
                    option_id=row['option_id'],passed=False,reason_code='revalidation_policy_unsupported',evaluation=None)
        results.append(result)
        if row['policy_id'] not in POLICIES:continue
        probe=SimpleNamespace(**vars(source));probe.draft=deepcopy(source.draft)
        record=next(r for r in probe.draft['records'] if r['layer_id']==row['layer_id'])
        if record['action']!='bind' or record['option_id']!=row['option_id'] or record['notes'].strip():
            result['reason_code']='revalidation_selection_changed'
            continue
        # Only the probe is reset. Other current selections remain evidence,
        # including ownership conflicts that must block a repeated adoption.
        record.update(action='pending',option_id=None)
        proposal=propose(probe)
        evaluation=next(r for r in proposal['rows'] if r['layer_id']==row['layer_id'])
        passed=(evaluation['status']=='eligible' and evaluation['option_id']==row['option_id']
                and bool(evaluation['checks']) and all(v is True for v in evaluation['checks'].values()))
        result.update(passed=passed,reason_code=None if passed else 'automatic_binding_revalidation_failed',
                      evaluation=dict(policy_id=proposal['policy_id'],limits=proposal['limits'],row=evaluation))
    return dict(schema='autospine.binding-revalidation/v1',profile='current-policy-replay-v1',
                authority='none',production_authorized=False,source_addresses=deepcopy(source.source_addresses),rows=results)
