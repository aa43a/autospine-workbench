"""Separate interpolation loss from unresolved solved poses in an exact experiment."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes())
    AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    evidence=json.loads((folder/'correction.json').read_bytes())
    if evidence['profile']!='adaptive-healthy-area-preservation-budget10-v1-experiment':
        raise ValueError('preservation_profile_required')
    check=evidence['refinement'][-1]['check'];rows=[]
    for slot in sorted({r['slot'] for r in check['failures']}):
        failures=[r for r in check['failures'] if r['slot']==slot]
        losses=[(f['minimum']-f['ratio'],r,f) for r in failures for f in r.get('preservation_failures',[])]
        worst=max(losses,key=lambda row:row[0]) if losses else None
        record=next(r for r in evidence['records'] if r['slot']==slot)
        local=Counter(r['local_constraints']['status'] for r in record['solver_samples'] if 'local_constraints' in r)
        rows.append(dict(slot=slot,failed_times=len(failures),key_failures=sum(r['at_key'] for r in failures),
            midpoint_failures=sum(not r['at_key'] for r in failures),
            ordinary_area_failures=sum(r['min_ratio']<.5 or r['max_ratio']>2 for r in failures),
            max_preservation_deficit=worst[0] if worst else 0,
            worst=dict(time=worst[1]['time'],at_key=worst[1]['at_key'],**worst[2]) if worst else None,
            tiny_deficits_le_1e_5=sum(d<=1e-5 for d,_,_ in losses),
            larger_deficits=sum(d>1e-5 for d,_,_ in losses),local_status_counts=dict(local)))
    result=dict(profile='preservation-failure-summary-v1',candidate=receipt['candidate_bundle_sha256'],
        authority='none',selected=False,sampled_frames=check['sampled_frames'],rows=rows,
        limitation='magnitude_buckets_are_diagnostic_not_relaxed_acceptance_thresholds')
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
