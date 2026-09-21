"""Check selected squat poses without treating a torso plane as real cloth depth."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.skirt_depth_probe import inspect


def run(evidence,output,surface=False):
    import re
    if not re.fullmatch('[a-f0-9]{64}',evidence):raise ValueError('experiment_identity_invalid')
    store=AnimatedStore(Path('workspace'));value=json.loads(store.read_file(evidence,'experiment.json'))
    identity=value['parent']['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh':raise ValueError('skirt_probe_source_unsupported')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map)
    duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    times=[duration*i/8 for i in range(9)]
    artifact=value['report']['candidate_bundle_sha256'];files=store.read(artifact)
    report=inspect(json.loads(files['skeleton.json']),files,sampler,times,surface=surface)
    report.update(artifact_sha256=artifact,experiment_sha256=evidence,times=times)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(report))
    print(json.dumps(dict(legs=report['legs'],skirts=report['skirts'],counts=dict(Counter(r['status'] for r in report['rows'])))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence');p.add_argument('output',type=Path)
    p.add_argument('--surface-envelope',action='store_true')
    a=p.parse_args();run(a.evidence,a.output,a.surface_envelope)
