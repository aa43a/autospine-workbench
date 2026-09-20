"""Measure a root contact-phase candidate against one immutable target artifact."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.contact_phase_candidate import build
from autospine_workbench.targets.character43.numeric_reference import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact_sha256')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    files = AnimatedStore(args.state_root).read(args.artifact_sha256)
    contact = json.loads(files['motion-contact.json'])
    original_motion = json.loads(files['motion-ir.json'])
    motion = deepcopy(original_motion)
    if original_motion['markers']:
        parser.error('requires unlabelled source with separate inferred windows')
    motion['markers'] = contact['hypothesis']['markers']
    times = [f['time'] for f in read(files)['animations']['external-motion']]
    _, report = build(json.loads(files['skeleton.json']), 'external-motion', motion,
                      times, contact['before']['drift_limit_px']*100)
    report.update(input_artifact_sha256=args.artifact_sha256,
                  input_motion_sha256=sha256(files['motion-ir.json']).hexdigest(),
                  input_contact_sha256=sha256(files['motion-contact.json']).hexdigest(),
                  before_max_drift_px=contact['before']['max_drift_px'],
                  runtime_validation='not_run', geometry_validation='not_run')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], reasons=report['reason_codes'],
                         after_max_drift_px=report['after']['max_drift_px'])))


if __name__ == '__main__':
    main()
