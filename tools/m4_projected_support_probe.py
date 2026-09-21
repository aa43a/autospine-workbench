"""Measure fixed-bend support feasibility on an exact full-chain candidate."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.projected_support_solver import solve


def run(folder,output):
    report=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(report['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json']);name='external-motion'
    evidence=json.loads(files['motion-review.json'])
    contact=json.loads(files['motion-contact.json'])
    intervals=contact['after']['intervals']
    times=sorted({s['time'] for r in intervals for s in r['samples']})
    records=[]
    for t in times:
        pose=matrices(doc,name,t);chains=[]
        for r in intervals:
            if not r['start']<=t<=r['end']:continue
            side=r['bone'].rsplit('_',1)[1]
            chains.append(dict(hip=pose['thigh_'+side][4:6],knee=pose['calf_'+side][4:6],
                               ankle=pose['foot_'+side][4:6],target=r['anchor']))
        if chains:
            row=solve(chains,evidence['reference_length_px']);row['time']=t;records.append(row)
    value=dict(profile='projected-support-feasibility-probe-v1',
        source_candidate_sha256=report['candidate_bundle_sha256'],authority='none',selected=False,
        frames=len(records),failed_frames=sum(r['status']!='candidate' for r in records),
        maximum_error_px=max(c['error_px'] for r in records for c in r['chains']),
        factor_range=[min(c['factor'] for r in records for c in r['chains']),
                      max(c['factor'] for r in records for c in r['chains'])],
        records=records,limitations=['independent_frames_not_an_animation','no_candidate_or_acceptance_changed'])
    with output.open('xb') as handle:handle.write(canonical_bytes(value))
    print(json.dumps({k:v for k,v in value.items() if k!='records'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.folder,args.output)
