"""Verify complete selected-region/body/time inventory before aggregating depth QA."""
import argparse
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes


def verify(report,checks,times):
    surfaces={s['slot']:s for s in report['inventory']['surfaces']}
    regions=report['regions']
    expected={(a,b) for a in regions for b in surfaces if a!=b}
    if len(set(regions))!=len(regions) or not set(regions)<=surfaces.keys():
        raise ValueError('region_coverage_regions')
    pairs={(p['arm'],p['body']):p for p in report['pairs']}
    if len(pairs)!=len(report['pairs']) or set(pairs)!=expected:
        raise ValueError('region_coverage_pair_inventory')
    if report['sampled_frames']!=len(times):raise ValueError('region_coverage_sample_count')
    grouped=defaultdict(list);counts=Counter();by_role={}
    for row in checks:grouped[row['arm'],row['body']].append(row)
    if set(grouped)!=expected:raise ValueError('region_coverage_check_inventory')
    for key,pair in pairs.items():
        rows=sorted(grouped[key],key=lambda r:r['time'])
        if [(r['time'],r['source_tick']) for r in rows]!=times:
            raise ValueError('region_coverage_time_inventory')
        summary=Counter(r['status'] for r in rows)
        if dict(summary)!=pair['status_counts'] or pair['sampled_frames']!=len(times):
            raise ValueError('region_coverage_pair_counts')
        if pair['role']!=surfaces[key[1]]['role']:raise ValueError('region_coverage_role')
        counts.update(summary);by_role.setdefault(pair['role'],Counter()).update(summary)
    if dict(counts)!=report['status_counts']:raise ValueError('region_coverage_total_counts')
    return dict(status='complete_selected_region_body_time_inventory',pairs=len(expected),
        sampled_frames=len(times),checks=len(checks),counts=dict(counts),
        by_role={k:dict(v) for k,v in by_role.items()},
        scope='measurement_completeness_not_depth_correctness_or_visual_acceptance')


def run(source,folder,output):
    if output.exists():raise ValueError('output_exists')
    raw=(folder/'report.json').read_bytes();report=json.loads(raw)
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    if report['source_artifact_sha256']!=digest:raise ValueError('region_coverage_source')
    files=AnimatedStore(source/'isolated-store').read(digest)
    pairs=json.loads(files['motion-depth.json'])['pairs'];schedule=None
    for pair in pairs:
        current=[(r['tick'],r['source_tick']) for r in pair['samples']]
        if schedule is not None and current!=schedule:raise ValueError('region_coverage_source_times')
        schedule=current
    if not schedule:raise ValueError('region_coverage_source_times')
    times=sorted([(t/1e6,s) for t,s in schedule]+[((a[0]+b[0])/2e6,(a[1]+b[1])/2)
        for a,b in zip(schedule,schedule[1:])])
    checks=[];hashes={}
    for region in report['regions']:
        if not region or Path(region).name!=region or '/' in region or '\\' in region:
            raise ValueError('region_coverage_name')
        data=(folder/(region+'.json')).read_bytes();rows=json.loads(data)
        if any(r['arm']!=region for r in rows):raise ValueError('region_coverage_checkpoint_scope')
        hashes[region]=sha256(data).hexdigest();checks.extend(rows)
    result=verify(report,checks,times)
    result.update(report_sha256=sha256(raw).hexdigest(),checkpoint_sha256=hashes,
                  source_artifact_sha256=digest,authority='none',selected=False)
    with output.open('xb') as stream:stream.write(canonical_bytes(result))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','folder','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.source,a.folder,a.output)
