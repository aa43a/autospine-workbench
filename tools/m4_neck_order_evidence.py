"""Explicit hypothetical neck evidence; never a production depth assertion."""
from m4_limb_region_order import constraints


def convert(report,partition,source_depth,*,kind='neck'):
    profiles={'neck':('neck-axis-thickness-sensitivity-v1','tested_radii','radius',[0,.02,.05,.1]),
              'skirt':('front-garment-depth-sensitivity-v1','tested_aspect_max','aspect_max',[.25,.5,.75,1.])}
    if kind not in profiles:raise ValueError('depth_hypothesis_kind')
    profile,inventory,parameter,expected=profiles[kind]
    if report.get('profile')!=profile or report.get(inventory)!=expected:
        raise ValueError('neck_hypothesis_profile')
    regions={r['slot']:r for r in partition['regions']};rows=[];pairs={};selected={}
    for row in report['rows']:
        region=regions[row['region']];selected[region['slot']]=region
        hypotheses=row['hypotheses']
        if [h[parameter] for h in hypotheses]!=expected:
            raise ValueError('neck_hypothesis_radius_inventory')
        if any(h['pair']!=[row['region'],row['body']] or h['time']!=row['time'] for h in hypotheses):
            raise ValueError('neck_hypothesis_sample_identity')
        # Require agreement across the declared radius sweep, retaining uncertainty.
        statuses={h['status'] for h in hypotheses}
        status=next(iter(statuses)) if len(statuses)==1 else 'requires_partition_or_more_depth'
        rows.append(dict(region=row['region'],source_slot=region['source_slot'],group=region['group'],
                         body=row['body'],time=row['time'],source_tick=row['source_tick'],status=status))
        key=(region['source_slot'],row['body'])
        if key not in pairs:
            parents=[p for p in source_depth['pairs'] if p['arm_slot']==key[0]]
            schedules=[[(r['tick'],r['source_tick']) for r in p['samples']] for p in parents]
            if not schedules or any(s!=schedules[0] for s in schedules[1:]):
                raise ValueError('neck_hypothesis_source_schedule')
            pairs[key]=dict(arm_slot=key[0],torso_slot=key[1],samples=parents[0]['samples'])
    if not rows:raise ValueError('neck_hypothesis_empty')
    result=constraints(dict(rows=rows),dict(regions=list(selected.values())),dict(pairs=list(pairs.values())))
    for pair in result['pairs']:pair['evidence_source']=('declared_neck_thickness_hypothesis_only'
        if kind=='neck' else 'declared_front_garment_envelope_hypothesis_only')
    return result['pairs']
