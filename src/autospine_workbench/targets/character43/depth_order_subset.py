"""Preserve conflicted regions while trying other proved sampled requirements."""
from .motion_depth_order import build as order_build


def build(document,animation,depth,probe,*,attempt_limit=4):
    remaining=list(depth['pairs']);attempts=[];excluded=[]
    for _ in range(attempt_limit):
        if not remaining:break
        candidate,report=order_build(document,animation,dict(depth,pairs=remaining),probe,refine_cycles=True)
        attempts.append(report)
        if candidate is not None:
            return candidate,dict(profile='bounded-conflict-preserving-order-subset-v1',
                status='partial_candidate' if excluded else 'candidate',attempts=attempts,excluded=excluded,
                retained_pairs=[[p['arm_slot'],p['torso_slot']] for p in remaining],
                authority='none',selected=False,scope='sampled_subset_with_unresolved_exceptions_not_full_depth_acceptance')
        if set(report['reason_codes'])!={'visible_unmapped_order_conflict'}:break
        implicated=set()
        for failure in report['failures']:
            for edge in failure.get('conflict',{}).get('edges',[]):
                if edge['source']!='uniform_sampled_local_depth':continue
                for pair in remaining:
                    if {edge['back'],edge['front']}=={pair['arm_slot'],pair['torso_slot']}:
                        implicated.add((pair['arm_slot'],pair['torso_slot']))
        if not implicated:break
        excluded.extend(dict(pair=list(pair),reason_code='visible_order_cycle_preserve_setup') for pair in sorted(implicated))
        remaining=[p for p in remaining if (p['arm_slot'],p['torso_slot']) not in implicated]
    return None,dict(profile='bounded-conflict-preserving-order-subset-v1',status='blocked',attempts=attempts,
        excluded=excluded,authority='none',selected=False,scope='no_order_candidate')
