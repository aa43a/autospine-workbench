"""Experimental root transport on a baked torso candidate; no automatic adoption."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.attachment_root_bake import build


def run(source, output, roots):
    receipt = json.loads((source/'report.json').read_bytes())
    files = AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    torso = json.loads(files['motion-torso-projection.json'])
    doc = json.loads(files['skeleton.json']); name = 'external-motion'
    reference_times = final_times(doc, name, [r['time'] for r in read(files)['animations'][name]])
    candidate, report = build(doc, name, torso, roots, reference_times,
        lambda row: print(json.dumps(row), flush=True))
    output.mkdir(parents=True,exist_ok=False)
    raw = canonical_bytes(candidate)
    (output/'skeleton.json').write_bytes(raw)
    report.update(source_candidate=receipt['candidate_bundle_sha256'],skeleton_sha256=sha256(raw).hexdigest())
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--root',action='append',required=True)
    args = parser.parse_args();run(args.source,args.output,args.root)
