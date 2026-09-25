"""Measure full-clip isolated torso candidates without modifying their bundles."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion2d.contact_candidate import infer
from autospine_workbench.targets.character43.final_motion_contact import for_candidate


def audit(files, artifact, runtime, bundle):
    provenance = json.loads(files['motion-torso-reference.json'])
    identity = provenance['source_identity']
    if (identity['clip_sha256'] != bundle.clip_sha256 or
            identity['bundle_sha256'] != bundle.bundle_sha256):
        raise ValueError('isolated_contact_source_mismatch')
    motion = bundle.motion
    document = json.loads(files['skeleton.json'])
    bones = {b['name']: b for b in document['bones']}
    length = sum(math.hypot(bones[n]['x'], bones[n]['y'])
                 for n in ('calf_l', 'foot_l', 'calf_r', 'foot_r')) / 2
    if not math.isfinite(length) or length <= 0:
        raise ValueError('isolated_contact_reference_invalid')
    contact = dict(selected=False, authority='none')
    if not any(m['kind'] == 'contact' for m in motion['markers']):
        if bundle.source_kind != 'bvh':
            raise ValueError('isolated_contact_unlabelled_source_unsupported')
        hypothesis = infer(parse_bvh(bundle.raw_bvh), bundle.bvh_map, source_up='+Y')
        if 'ticks_per_second' not in hypothesis:
            raise ValueError('isolated_contact_hypothesis_unavailable')
        contact['hypothesis'] = hypothesis
    # Supply measurement inputs in memory only. The immutable candidate and its
    # acceptance remain untouched. for_candidate verifies skeleton and frame grid;
    # recheck rejects cropped clips whose end differs from the verified full clip.
    inputs = dict(files)
    inputs.update({'motion-ir.json': canonical_bytes(motion),
                   'motion-contact.json': canonical_bytes(contact),
                   'motion-review.json': canonical_bytes({'reference_length_px': length})})
    result = for_candidate(inputs, artifact, runtime)
    result.update(profile='isolated-full-clip-contact-audit-v1',
                  source_identity=identity, reference_length_px=length,
                  correction_applied=False, production_authorized=False,
                  scope='source_windows_and_final_ankle_proxy_not_sole_or_visual_acceptance')
    return result


def run(folder, state, output):
    receipt = json.loads((folder / 'report.json').read_bytes())
    artifact = receipt['candidate_bundle_sha256']
    files = AnimatedStore(folder / 'isolated-store').read(artifact)
    provenance = json.loads(files['motion-torso-reference.json'])
    identity = provenance['source_identity']
    if receipt['source_identity'] != identity:
        raise ValueError('isolated_contact_receipt_mismatch')
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    raw = (folder / 'runtime/report.json').read_bytes()
    result = audit(files, artifact, json.loads(raw), bundle)
    result['runtime_report_sha256'] = sha256(raw).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(canonical_bytes(result))
    print(json.dumps(dict(status=result['status'], frames=result['final_timeline_check']['samples'],
                         max_drift_px=result['after']['max_drift_px'],
                         limit_px=result['after']['drift_limit_px'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    run(args.folder, args.state, args.output)
