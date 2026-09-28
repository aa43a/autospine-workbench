"""Translate complete surface observations into constraints or explicit setup holds."""
from collections import defaultdict


ROLES={'torso','arm.l','arm.r','leg.l','leg.r'}
STATUSES={'no_overlap','uniform_front_proxy','uniform_back_proxy','requires_partition_or_more_depth','unmeasured'}


def build(inventory,checks,times):
    roles={s['slot']:s['role'] for s in inventory['surfaces']};grouped=defaultdict(list)
    if not times or len(times)%2!=1 or any(b[0]<=a[0] for a,b in zip(times,times[1:])):
        raise ValueError('surface_order_schedule_invalid')
    for row in checks:
        if row['arm'] not in roles or row['body'] not in roles or row['arm']==row['body']:
            raise ValueError('surface_order_slot_inventory')
        if row['status'] not in STATUSES:raise ValueError('surface_order_status_invalid')
        grouped[row['arm'],row['body']].append(row)
    pairs=[];held=[];nonoverlap=[]
    for (arm,body),rows in sorted(grouped.items()):
        rows=sorted(rows,key=lambda r:r['time'])
        if [(r['time'],r['source_tick']) for r in rows]!=times:
            raise ValueError('surface_order_time_inventory')
        if all(r['status']=='no_overlap' for r in rows):
            nonoverlap.append([arm,body]);continue
        if roles[body] not in ROLES:
            held.append(dict(arm=arm,body=body,role=roles[body],policy='preserve_visible_setup_order'))
            continue
        samples=[]
        for row in rows:
            status=row['status']
            samples.append(dict(tick=row['time']*1e6,source_tick=row['source_tick'],
                ambiguous=status not in ('no_overlap','uniform_front_proxy','uniform_back_proxy'),
                support='no_overlap' if status=='no_overlap' else 'sampled',
                current_front_slot=body if status=='uniform_back_proxy' else arm))
        for i in range(0,len(samples)-1,2):samples[i]['interval_sample']=samples[i+1]
        pairs.append(dict(arm_slot=arm,torso_slot=body,samples=samples[::2],
                          evidence_source='complete_surface_inventory_same_frame_proxy'))
    return dict(pairs=pairs,held=held,nonoverlap=nonoverlap,strict_interval_evidence=True)


def merge(base,extra):
    """Do not silently overwrite conflicting evidence from another diagnostic."""
    pairs={(p['arm_slot'],p['torso_slot']):p for p in base['pairs']}
    if len(pairs)!=len(base['pairs']):raise ValueError('surface_order_duplicate_base')
    seen=set()
    for pair in extra['pairs']:
        key=(pair['arm_slot'],pair['torso_slot'])
        if key in seen:raise ValueError('surface_order_duplicate_supplement')
        seen.add(key)
        if key in pairs and pairs[key]['samples']!=pair['samples']:
            raise ValueError('surface_order_conflicting_observations')
        pairs[key]=pair
    return dict(pairs=list(pairs.values()),strict_interval_evidence=True)
