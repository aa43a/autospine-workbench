"""Measure final pose fidelity of a verified deform-only corrective."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_pose import measure, summary
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from m4_register_corrective_candidate import receipt_for


def run(state, source, corrected, output):
    if output.exists():
        raise ValueError('corrective_pose_output_exists')
    read = lambda p: json.loads(p.read_bytes())
    original = read(source/'report.json'); final = read(corrected/'report.json')
    old = AnimatedStore(source/'isolated-store').read(original['candidate_bundle_sha256'])
    files = AnimatedStore(corrected/'isolated-store').read(final['candidate_bundle_sha256'])
    request = read(source/'request.json'); runtime = read(corrected/'runtime/report.json')
    receipt_for(request, original, old, final, files, runtime)
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    report = measure(files, final['candidate_bundle_sha256'], bundle, request)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as f:
        f.write(canonical_bytes(report))
    print(json.dumps(summary(report, report['artifact_sha256'], report['skeleton_sha256'],
        identity, report['source_request_sha256']), ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('state', 'source', 'corrected', 'output'):
        p.add_argument(name, type=Path)
    a = p.parse_args(); run(a.state, a.source, a.corrected, a.output)
