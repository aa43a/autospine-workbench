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
    parser.add_argument('--contact-root', action='store_true', help='Try bounded ankle-proxy root correction; not sole locking')
    parser.add_argument('--publish', action='store_true', help='Publish an isolated diagnostic bundle for official capture')
    parser.add_argument('--samples', type=int, default=125)
    parser.add_argument('--foreshortening', action='store_true', help='Add source projected limb length candidates')
    parser.add_argument('--repair-area', action='store_true', help='Try bounded mixed-weight affine deformation')
    parser.add_argument('--convergent-area', action='store_true', help='Use bounded v2 area solver (requires repair-area)')
    args = parser.parse_args()
    if args.convergent_area and not args.repair_area:
        parser.error('convergent-area requires repair-area')
    if not 3 <= args.samples <= 1025:
        parser.error('samples must be 3..1025')
    files = AnimatedStore(args.state_root).read(args.character)
    motion_bundle = VerifiedMotionBundleReader(args.state_root).load(args.motion, args.motion_bundle)
    motion = json.loads((motion_bundle.path/'motion.json').read_bytes())
    document, evidence = build(json.loads(files['skeleton.json']), motion, 'walk')
    document['animations'] = {'walk': document['animations']['walk']}
    if args.foreshortening:
        from autospine_workbench.bvh_parser import parse_bvh
        from autospine_workbench.targets.character43.projected_lengths import build as add_lengths
        document, lengths = add_lengths(document, 'walk', parse_bvh((motion_bundle.path/'source.bvh').read_bytes()),
                                        json.loads((motion_bundle.path/'map.json').read_bytes()))
        evidence['projected_lengths'] = lengths
    if args.repair_area:
        from autospine_workbench.targets.character43.affine_area_repair import repair
        document, correction_area = repair(document, 'walk', convergent=args.convergent_area)
        evidence['area_repair'] = correction_area
    args.output.mkdir(parents=True, exist_ok=True)
    if args.contact_root:
        from autospine_workbench.targets.character43.contact_root_candidate import build as correct_root
        intervals = [dict(limb=m['limb'], start=m['start_tick']/motion['ticks_per_second'],
                          end=m['end_tick']/motion['ticks_per_second']) for m in motion['markers']
                     if m['kind'] == 'contact' and m['limb'] in ('leg.left', 'leg.right')]
        corrected, correction = correct_root(document, 'walk', intervals,
                                             reference_length=evidence['reference_length_px'])
        (args.output/'root-correction.json').write_bytes(canonical_bytes(correction))
        if corrected is None:
            raise ValueError('character_contact_root_candidate_blocked')
        document = corrected
        evidence['root_correction_profile'] = correction['profile']
    duration = motion['duration_ticks']/motion['ticks_per_second']
    times = [duration*i/(args.samples-1) for i in range(args.samples)]
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
    if args.publish:
        # Keep texture bytes, not previous animation-specific reports or authority.
        package = {n: data for n, data in files.items() if n.endswith('.png') or n == 'skeleton.atlas'}
        package.update({'skeleton.json': raw, 'numeric-reference.json': reference,
                        'motion-review.json': canonical_bytes(evidence),
                        'deformation.json': canonical_bytes(qa), 'motion-ir.json': canonical_bytes(motion)})
        if args.contact_root:
            package['root-correction.json'] = canonical_bytes(correction)
        manifest = dict(schema='autospine.character-motion-preview/v1', profile='isolated-motionir-preview-v1',
                        authority='none', production_authorized=False, animations=['walk'],
                        source_character_sha256=args.character, source_motion_bundle_sha256=args.motion_bundle,
                        status='preview_only', files={n: sha256(data).hexdigest() for n, data in package.items()})
        package['character-manifest.json'] = canonical_bytes(manifest)
        digest = AnimatedStore(args.state_root).publish(package)
        (args.output/'published.json').write_bytes(canonical_bytes(dict(bundle_sha256=digest)))
        print(json.dumps(dict(bundle_sha256=digest)))


if __name__ == '__main__':
    main()
