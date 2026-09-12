"""Generate a non-adopted whole-character MotionIR preview and sampled diagnostics."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.motionir_candidate import build, sample
from autospine_workbench.targets.character43.deformation_qa import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--motion', required=True)
    parser.add_argument('--motion-bundle', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = AnimatedStore(args.state_root).read(args.character)
    motion_bundle = VerifiedMotionBundleReader(args.state_root).load(args.motion, args.motion_bundle)
    motion = json.loads((motion_bundle.path/'motion.json').read_bytes())
    document, evidence = build(json.loads(files['skeleton.json']), motion, 'walk')
    document['animations'] = {'walk': document['animations']['walk']}
    duration = motion['duration_ticks']/motion['ticks_per_second']
    times = [duration*i/124 for i in range(125)]
    frames = [dict(time=t, vertices=sample(document, 'walk', t)[0]) for t in times]
    raw = canonical_bytes(document)
    reference = canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(), animations={'walk': frames}))
    qa = inspect({'skeleton.json': raw, 'numeric-reference.json': reference})
    contacts = []
    for marker in motion['markers']:
        if marker['kind'] != 'contact' or marker['limb'] not in ('leg.left', 'leg.right'):
            continue
        a, b = (marker[k]/motion['ticks_per_second'] for k in ('start_tick', 'end_tick'))
        side = 'l' if marker['limb'] == 'leg.left' else 'r'
        # An ankle proxy cannot certify toe/sole locking; preserve this distinction.
        points = [sample(document, 'walk', a+(b-a)*i/32)[1]['foot_'+side][:2] for i in range(32)]
        import math
        drift = max(math.dist(points[0], p) for p in points)
        contacts.append(dict(limb=marker['limb'], start=a, end=b, ankle_proxy_drift_px=drift,
                             normalized_reference_drift=drift/evidence['reference_length_px']))
    evidence.update(character_sha256=args.character, motion_bundle_sha256=args.motion_bundle,
                    geometry_passed=qa['passed'], ankle_proxy_contacts=contacts,
                    runtime_status='not_evaluated', contact_status='toe_anchor_unavailable')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in [('skeleton.json', raw), ('numeric-reference.json', reference),
                       ('motion-review.json', canonical_bytes(evidence)),
                       ('deformation.json', canonical_bytes(qa))]:
        (args.output/name).write_bytes(data)
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()
