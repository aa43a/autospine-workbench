"""Compare identical regional sample inventories; never infer quality acceptance."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def samples(report):
    regional=report['depth']['regional'];result={}
    groups=[('refinement',r['pair'],r) for r in regional['refinement']['rows']]
    for section,other in [('cloth_constraints','cloth'),('limb_constraints','leg')]:
        for pair in (regional.get(section) or {}).get('pairs',[]):
            groups.extend((section,[pair['arm'],pair[other]],r) for r in pair['rows'])
    for section,pair,row in groups:
        for check in row['checks']:
            key=(section,tuple(pair),row.get('tick'),check['time'])
            if key in result:raise ValueError('duplicate_regional_sample')
            result[key]=check
    return result


def compare(before,after):
    for name in ('source_job','source_artifact_sha256','request_sha256','motion_identity'):
        if before[name]!=after[name]:raise ValueError('regional_comparison_source_changed')
    a,b=samples(before),samples(after)
    if a.keys()!=b.keys():raise ValueError('regional_comparison_sample_inventory_changed')
    recovered=remaining=preserved=0
    for key,old in a.items():
        new=b[key]
        if old['status']=='unmeasured':
            remaining+=new['status']=='unmeasured'
            recovered+=new['status']!='unmeasured'
        else:
            if any(old.get(k)!=new.get(k) for k in ('status','counts','overlap_pixels')):
                raise ValueError('regional_comparison_measurement_changed:'+str(key))
            preserved+=1
    return dict(sample_inventory=len(a),preserved_measured_samples=preserved,
        recovered_samples=recovered,remaining_unmeasured_samples=remaining,
        authority='none',adoption_allowed=False,
        scope='same_recorded_sample_outcomes_not_continuous_geometry_or_visual_acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path)
    parser.add_argument('output',type=Path);args=parser.parse_args()
    old,new=args.before.read_bytes(),args.after.read_bytes()
    result=compare(json.loads(old),json.loads(new))
    result.update(before_sha256=sha256(old).hexdigest(),after_sha256=sha256(new).hexdigest())
    with args.output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    print(json.dumps(result))
