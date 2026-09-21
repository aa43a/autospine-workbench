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


def interval_failures(outcome,ordered):
    if not outcome.get('strict_interval_evidence'):return []
    models=json.loads((ordered/'inference.json').read_bytes())
    regions={r['slot']:r for r in outcome['partition']['regions']};records=[]
    for failure in outcome['order']['failures']:
        if failure['reason_code']!='visible_depth_order_changes_within_interval':continue
        arm,body=failure['pair'];region=regions[arm];source_body=regions.get(body,{}).get('source_slot',body)
        samples=[]
        for witness in failure['samples']:
            time=witness['overlap']['time']
            matches=[f for f in models[region['source_slot']][source_body] if abs(f['time']-time)<1e-12]
            if len(matches)!=1:raise ValueError('surface_audit_interval_witness_time')
            frame=matches[0];states=dict(Counter(frame['observed_states'][i] for i in region['triangles']))
            samples.append(dict(time=time,source_tick=frame['source_tick'],observed_states=states))
        records.append(dict(time=failure['time'],pair=failure['pair'],samples=samples,
                            includes_ambiguous_inference=any('A' in s['observed_states'] for s in samples),
                            hard_proxy_only=all(set(s['observed_states'])<=set('FB') for s in samples)))
    return records


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
    subdivisions=report.get('source_subdivisions',2)
    if subdivisions not in (2,4):raise ValueError('surface_audit_subdivisions')
    times={(t/1e6,s) for t,s in ticks}|{((a[0]+(b[0]-a[0])*i/subdivisions)/1e6,a[1]+(b[1]-a[1])*i/subdivisions)
          for a,b in zip(ticks,ticks[1:]) for i in range(1,subdivisions)}
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
    if sha256((ordered/'partition.json').read_bytes()).hexdigest()!=outcome['partition_skeleton_sha256']:
        raise ValueError('surface_audit_partition_identity')
    if outcome.get('strict_interval_evidence'):
        if subdivisions!=4 or outcome['order'].get('interval_evidence_policy')!='same-time-source-and-held-midpoint-v1':
            raise ValueError('surface_audit_interval_policy')
        if outcome['sampled_frames']!=len(times):raise ValueError('surface_audit_geometry_sample_count')
    return dict(source_artifact_sha256=report['source_artifact_sha256'],trace_report_sha256=sha256(raw).hexdigest(),
        inventory_counts=dict(Counter(r['role'] for r in report['inventory']['surfaces'])),pair_count=len(expected),
        sampled_times=len(times),checks=len(checks),status_counts=report['status_counts'],
        unmeasured_reasons=dict(Counter(r.get('reason_code') for r in checks if r['status']=='unmeasured')),
        held_setup_pairs=held,relation_pair_count=outcome['relation_pair_count'],coherent=coherent_audit(ordered),
        interval_evidence_policy=outcome['order'].get('interval_evidence_policy'),
        relation_pruning=outcome.get('relation_pruning',{}),source_subdivisions=subdivisions,
        interval_reversal_evidence=interval_failures(outcome,ordered))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('folders',nargs='+',type=Path);args=parser.parse_args()
    if len(args.folders)%2:parser.error('Expected trace/coherent directory pairs')
    result=dict(profile='source-surface-coverage-audit-v1',experiments=[audit(*args.folders[i:i+2]) for i in range(0,len(args.folders),2)])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
