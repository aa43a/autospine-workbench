"""Bounded order generation retaining opaque-boundary exceptions at setup order."""
from .depth_order_subset import build as subset_build


def build(document,animation,depth,probe,inspect,*,attempt_limit=4):
    remaining=list(depth['pairs']);attempts=[];excluded=[]
    for _ in range(attempt_limit):
        if not remaining:break
        candidate,subset=subset_build(document,animation,dict(depth,pairs=remaining),probe)
        entry=dict(subset=subset);attempts.append(entry)
        if candidate is None:break
        check=inspect(candidate);entry['continuity']=check
        if check['status']=='incomplete':break
        if check['status']=='no_sampled_cut':
            unchanged=candidate==document
            return (None if unchanged else candidate),dict(profile='sampled-order-continuity-guard-v1',
                status='no_supported_order_change' if unchanged else 'partial_candidate' if excluded or subset['excluded'] else 'candidate',
                attempts=attempts,excluded=excluded,authority='none',selected=False,
                scope='sampled_no_new_opaque_boundary_not_full_visibility_or_visual_acceptance')
        if check['status']!='needs_review':break
        implicated={(r['changed_region'],r['body']) for r in check['records']}
        available={(p['arm_slot'],p['torso_slot']) for p in remaining}
        if not implicated or not implicated<=available:break
        excluded.extend(dict(pair=list(pair),reason_code='new_opaque_boundary_preserve_setup') for pair in sorted(implicated))
        remaining=[p for p in remaining if (p['arm_slot'],p['torso_slot']) not in implicated]
    return None,dict(profile='sampled-order-continuity-guard-v1',status='blocked',attempts=attempts,
        excluded=excluded,authority='none',selected=False,scope='no_order_candidate')
