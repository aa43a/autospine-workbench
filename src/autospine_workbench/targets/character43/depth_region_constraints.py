"""Translate source-surface trace labels to both sides of a render partition."""
from collections import Counter

PROFILE='bidirectional-partition-region-constraints-v1-experiment'


def build(partition,models,*,pair_limit=4096,interval_depth=False,diagnostics=None,overlap_possible=None):
    replacements={}
    for region in partition['regions']:
        replacements.setdefault(region['source_slot'],[]).append(region['slot'])
    pairs=[]
    regions={r['slot']:r for r in partition['regions']}
    def inactive(region,frames):
        return all(frame['observed_states'][t]=='N' for frame in frames for t in region['triangles'])
    def simultaneous(region,frames,target,reverse):
        if len(frames)!=len(reverse):raise ValueError('region_constraint_reverse_times')
        possible=False
        for a,b in zip(frames,reverse):
            if (a['time'],a['source_tick'])!=(b['time'],b['source_tick']):raise ValueError('region_constraint_reverse_times')
            possible |= (any(a['observed_states'][t]!='N' for t in region['triangles']) and
                         any(b['observed_states'][t]!='N' for t in target['triangles']))
        return possible
    for region in partition['regions']:
        for body,frames in models[region['source_slot']].items():
            # With no sampled support, keep the ordinary setup-order guard instead.
            if inactive(region,frames):continue
            targets=replacements.get(body,[body])
            reverse=models.get(body,{}).get(region['source_slot'])
            if reverse is not None:targets=[t for t in targets if not inactive(regions[t],reverse)]
            if reverse is not None and interval_depth:
                retained=[t for t in targets if simultaneous(region,frames,regions[t],reverse)]
                if diagnostics is not None:
                    key='pairs_disjoint_at_all_depth_samples'
                    diagnostics[key]=diagnostics.get(key,0)+len(targets)-len(retained)
                targets=retained
                if overlap_possible is not None:
                    retained=[t for t in targets if overlap_possible(region['slot'],t,frames)]
                    if diagnostics is not None:
                        key='pairs_disjoint_at_all_sampled_bounds'
                        diagnostics[key]=diagnostics.get(key,0)+len(targets)-len(retained)
                    targets=retained
            if len(pairs)+len(targets)>pair_limit:raise ValueError('region_constraint_pair_limit')
            for target in targets:
                samples=[]
                for frame in frames:
                    values={frame['labels'][t] for t in region['triangles']}
                    if len(values)!=1:raise ValueError('coherent_partition_signature_changed')
                    samples.append(dict(tick=frame['time']*1e6,source_tick=frame['source_tick'],
                        ambiguous=any(frame['observed_states'][t] in 'UM' for t in region['triangles']),
                        support='no_overlap' if all(frame['observed_states'][t]=='N' for t in region['triangles']) else 'sampled',
                        evidence_states=dict(Counter(frame['observed_states'][t] for t in region['triangles'])),
                        current_front_slot=region['slot'] if values.pop() else target))
                if interval_depth:
                    if len(samples)%2!=1:raise ValueError('interval_depth_sample_inventory')
                    for i in range(0,len(samples)-2,2):
                        if abs(samples[i+1]['tick']-(samples[i]['tick']+samples[i+2]['tick'])/2)>1e-6:
                            raise ValueError('interval_depth_midpoint_missing')
                        samples[i]['interval_sample']=samples[i+1]
                    samples=samples[::2]
                pairs.append(dict(arm_slot=region['slot'],torso_slot=target,
                    evidence_source='regularized_proxy_inference',source_pair=[region['source_slot'],body],samples=samples))
    return pairs
