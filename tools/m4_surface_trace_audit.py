"""Verify complete source-surface coverage before reporting coherent outcomes."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_surface_inventory import build,route
from m4_coherent_inference_audit import audit as coherent_audit


def audit(folder,ordered):
    raw=(folder/'report.json').read_bytes();report=json.loads(raw)
    observations_raw=(folder/'observations.json').read_bytes();checks_raw=(folder/'checks.json').read_bytes()
    if sha256(observations_raw).hexdigest()!=report['observations_sha256'] or sha256(checks_raw).hexdigest()!=report['checks_sha256']:
        raise ValueError('surface_audit_trace_identity')
    files=AnimatedStore(Path('workspace')).read(report['source_artifact_sha256'])
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    if build(document)!=report['inventory']:raise ValueError('surface_audit_inventory')
    arms={p['arm_slot'] for p in depth['pairs']};names={s['name'] for s in document['slots']}
    expected={(a,b) for a in arms for b in names if a!=b}
    if len(report['pairs'])!=len(expected) or {(p['arm'],p['body']) for p in report['pairs']}!=expected:
        raise ValueError('surface_audit_pair_coverage')
    source={r['tick']:r['source_tick'] for p in depth['pairs'] for r in p['samples']};ticks=sorted(source.items())
    times={(t/1e6,s) for t,s in ticks}|{((a[0]+b[0])/2e6,(a[1]+b[1])/2) for a,b in zip(ticks,ticks[1:])}
    checks=json.loads(checks_raw);by_pair={p:[] for p in expected}
    for row in checks:by_pair[row['arm'],row['body']].append(row)
    for pair,rows in by_pair.items():
        if len(rows)!=len(times) or {(r['time'],r['source_tick']) for r in rows}!=times:
            raise ValueError('surface_audit_time_coverage')
        receipt=next(p for p in report['pairs'] if (p['arm'],p['body'])==pair)
        if dict(Counter(r['status'] for r in rows))!=receipt['status_counts']:raise ValueError('surface_audit_pair_counts')
    if dict(Counter(r['status'] for r in checks))!=report['status_counts']:raise ValueError('surface_audit_counts')
    observations=json.loads(observations_raw);selected,held=route(observations,report['inventory'])
    outcome=json.loads((ordered/'report.json').read_bytes())
    if (outcome['parent_report_sha256']!=sha256(raw).hexdigest() or outcome['held_setup_pairs']!=held
            or outcome['observations_sha256']!=report['observations_sha256'] or not outcome['surface_routing']):
        raise ValueError('surface_audit_order_identity')
    return dict(source_artifact_sha256=report['source_artifact_sha256'],trace_report_sha256=sha256(raw).hexdigest(),
        inventory_counts=dict(Counter(r['role'] for r in report['inventory']['surfaces'])),pair_count=len(expected),
        sampled_times=len(times),checks=len(checks),status_counts=report['status_counts'],
        unmeasured_reasons=dict(Counter(r.get('reason_code') for r in checks if r['status']=='unmeasured')),
        held_setup_pairs=held,relation_pair_count=outcome['relation_pair_count'],coherent=coherent_audit(ordered))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('folders',nargs='+',type=Path);args=parser.parse_args()
    if len(args.folders)%2:parser.error('Expected trace/coherent directory pairs')
    result=dict(profile='source-surface-coverage-audit-v1',experiments=[audit(*args.folders[i:i+2]) for i in range(0,len(args.folders),2)])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
