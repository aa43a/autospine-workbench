"""Evaluate one explicitly selected supported suffix; retain all unresolved evidence."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build


def select(depth, arm, start):
    if not depth.get('strict_interval_evidence'):
        raise ValueError('interval_evidence_required')
    pairs = [p for p in depth['pairs'] if p['arm_slot'] == arm]
    if len(pairs) != 1:
        raise ValueError('unique_arm_pair_required')
    pair = deepcopy(pairs[0])
    selected = [s for s in pair['samples'] if s['tick']/1e6 >= start]
    if not selected or abs(selected[0]['tick']/1e6-start) > 1e-9:
        raise ValueError('exact_interval_start_required')
    for row in selected:
        for sample in (row, row.get('interval_sample')):
            if sample is not None and (sample.get('ambiguous') or
                    sample.get('support') != 'uniform_front_proxy'):
                raise ValueError('suffix_not_uniform_front')
    pair['samples'] = selected
    result = deepcopy(depth)
    result['pairs'] = [pair]
    return result


def run(source, evidence, output, arm, start):
    receipt = json.loads((source/'report.json').read_bytes())
    raw = evidence.read_bytes(); depth = json.loads(raw)
    digest = receipt['candidate_bundle_sha256']
    if depth['candidate_bundle_sha256'] != digest or depth['source_identity'] != receipt['source_identity']:
        raise ValueError('interval_candidate_identity_mismatch')
    selected = select(depth, arm, start)
    files = AnimatedStore(source/'isolated-store').read(digest)
    document = json.loads(files['skeleton.json'])
    probe = Probe(document, files, 'external-motion', tiled=True, rendered_bounds=True,
                  sparse='priority_depth_points')
    candidate, report = build(document, 'external-motion', selected, probe, refine_cycles=True)
    report.update(parent=digest, source_identity=receipt['source_identity'],
                  depth_sha256=sha256(raw).hexdigest(), arm=arm, start=start,
                  candidate_available=candidate is not None,
                  scope='selected_suffix_crossing_guard_not_full_motion_or_switch_visual_acceptance',
                  unresolved_evidence_preserved=True, switch_visual_status='not_evaluated')
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'source-depth.json').write_bytes(raw)
    if candidate is not None:
        before = deepcopy(document); after = deepcopy(candidate)
        after['animations']['external-motion'].pop('drawOrder', None)
        if before != after:
            raise ValueError('interval_changed_non_order_channels')
        (output/'skeleton-candidate.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(candidate=report['candidate_available'], reasons=report['reason_codes'],
                          failures=len(report['failures']), frames=report['frames'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'evidence', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--arm', required=True)
    parser.add_argument('--start', required=True, type=float)
    args = parser.parse_args()
    run(args.source, args.evidence, args.output, args.arm, args.start)
