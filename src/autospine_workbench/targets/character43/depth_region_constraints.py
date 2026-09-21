"""Translate source-surface trace labels to both sides of a render partition."""

PROFILE='bidirectional-partition-region-constraints-v1-experiment'


def build(partition,models,*,pair_limit=4096):
    replacements={}
    for region in partition['regions']:
        replacements.setdefault(region['source_slot'],[]).append(region['slot'])
    pairs=[]
    regions={r['slot']:r for r in partition['regions']}
    def inactive(region,frames):
        return all(frame['observed_states'][t]=='N' for frame in frames for t in region['triangles'])
    for region in partition['regions']:
        for body,frames in models[region['source_slot']].items():
            # With no sampled support, keep the ordinary setup-order guard instead.
            if inactive(region,frames):continue
            targets=replacements.get(body,[body])
            reverse=models.get(body,{}).get(region['source_slot'])
            if reverse is not None:targets=[t for t in targets if not inactive(regions[t],reverse)]
            if len(pairs)+len(targets)>pair_limit:raise ValueError('region_constraint_pair_limit')
            for target in targets:
                samples=[]
                for frame in frames:
                    values={frame['labels'][t] for t in region['triangles']}
                    if len(values)!=1:raise ValueError('coherent_partition_signature_changed')
                    samples.append(dict(tick=frame['time']*1e6,source_tick=frame['source_tick'],
                        ambiguous=any(frame['observed_states'][t] in 'UM' for t in region['triangles']),
                        current_front_slot=region['slot'] if values.pop() else target))
                pairs.append(dict(arm_slot=region['slot'],torso_slot=target,
                    evidence_source='regularized_proxy_inference',source_pair=[region['source_slot'],body],samples=samples))
    return pairs
