"""Explain local depth abstentions without treating missing samples as correct."""
from collections import Counter


def summarize(records):
    groups={};seen=set()
    for row in records:
        pair=tuple(row['pair']);check=row['check'];time=check['time']
        key=(*pair,time)
        if key in seen:raise ValueError('local_depth_duplicate_sample')
        seen.add(key)
        group=groups.setdefault(pair,dict(samples=0,reasons=Counter(),pixels=Counter()))
        group['samples']+=1
        state=check['status']
        if state=='unmeasured':
            reason='unmeasured:'+check['reason_code']
        elif state=='no_overlap':
            reason='no_visible_overlap'
        else:
            counts=check['counts']
            ambiguity=check.get('ambiguity_causes')
            if ambiguity:
                if (any(type(v) is not int or v<0 for v in ambiguity.values())
                        or sum(ambiguity.values())!=counts['ambiguous']):
                    raise ValueError('local_depth_ambiguity_inventory')
                group.setdefault('ambiguity',Counter()).update(ambiguity)
            if (set(counts)!={'front','back','ambiguous','unknown'}
                    or any(type(v) is not int or v<0 for v in counts.values())
                    or sum(counts.values())!=check['overlap_pixels']):
                raise ValueError('local_depth_pixel_inventory')
            if state not in ('uniform_front_proxy','uniform_back_proxy','requires_partition_or_more_depth'):
                raise ValueError('local_depth_status_unsupported')
            group['pixels'].update(counts)
            if counts['unknown']:reason='missing_depth_support'
            elif counts['front'] and counts['back']:reason='mixed_front_back_support'
            elif counts['ambiguous']:reason='depth_margin_ambiguity'
            elif counts['front']:reason='uniform_front_proxy'
            else:reason='uniform_back_proxy'
        group['reasons'][reason]+=1
    return dict(profile='local-depth-cause-summary-v1',pairs=[dict(pair=list(pair),samples=g['samples'],
        reasons=dict(g['reasons']),pixel_observations=dict(g['pixels']),
        **({'ambiguity_causes':dict(g['ambiguity'])} if 'ambiguity' in g else {})) for pair,g in groups.items()],
        authority='none',selected=False,scope='sampled_proxy_causes_not_depth_truth_or_error_rate')
