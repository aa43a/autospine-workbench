"""Preserve a solved diagnostic and its exact QA grid before a bounded reader rejects it.

This does not publish a candidate or run/approve geometry, contact, or Runtime QA.
The request and frozen source scope are verified by the normal selected builder.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43 import limb_transverse_candidate as candidate
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.selected_transverse_candidate import build


def inventory(document, name, parent_times):
    animation = document['animations'][name]
    keys = {k['time'] for tracks in animation['bones'].values() for values in tracks.values() for k in values}
    keys.update(k['time'] for skin in animation.get('attachments', {}).values() for slots in skin.values()
                for tracks in slots.values() for values in tracks.values() for k in values)
    keys = sorted(keys)
    halves = sorted(set(keys) | {(a+b)/2 for a, b in zip(keys, keys[1:])})
    quarters = sorted(set(halves) | {(a+b)/2 for a, b in zip(halves, halves[1:])})
    times = sorted(set(quarters) | set(parent_times))
    gaps = [b-a for a, b in zip(keys, keys[1:])]
    return dict(key_count=len(keys), half_sample_count=len(halves), quarter_sample_count=len(quarters),
        parent_sample_count=len(set(parent_times)), final_sample_count=len(times),
        minimum_key_interval=min(gaps) if gaps else None,
        subnanosecond_key_intervals=sum(g < 1e-9 for g in gaps),
        reader_limit=4097, exceeds_reader_limit=len(times) > 4097, times=times)


class ProbeComplete(Exception):
    pass


def run(state_root, request_path, output):
    request = json.loads(request_path.read_bytes()); repair = request['repair_execution']
    plan = repair['draft']
    if (sha256(canonical_bytes(plan)).hexdigest() != repair['draft_sha256']
            or plan['artifact_sha256'] != repair['parent_artifact_sha256']
            or plan['transverse_repair']['character_sha256'] != request['character_sha256']):
        raise ValueError('probe_request_identity_changed')
    output.mkdir(parents=True, exist_ok=False)
    store = AnimatedStore(state_root); files = store.read(repair['parent_artifact_sha256'])
    character = store.read(request['character_sha256'])
    parent_times = [f['time'] for f in read(files)['animations'][plan['animation']]]
    records = []; original = candidate.correct_joints
    def solve(*args, **kwargs):
        solved, evidence = original(*args, **kwargs)
        records.append(evidence)
        return solved, evidence
    def capture(document, name, unused):
        raw = canonical_bytes(document)
        (output/'solved-diagnostic.json').write_bytes(raw)
        report = inventory(document, name, parent_times)
        times = report.pop('times'); time_bytes = canonical_bytes(times)
        (output/'validation-times.json').write_bytes(time_bytes)
        report.update(parent_artifact_sha256=repair['parent_artifact_sha256'],
            request_sha256=sha256(request_path.read_bytes()).hexdigest(),
            skeleton_sha256=sha256(raw).hexdigest(), times_sha256=sha256(time_bytes).hexdigest(),
            slot=plan['slot'], solver_records=records, status='diagnostic_only',
            geometry_status='not_evaluated', runtime_status='not_evaluated', authority='none', selected=False)
        (output/'report.json').write_bytes(canonical_bytes(report))
        print(json.dumps({k:v for k,v in report.items() if k!='solver_records'}), flush=True)
        raise ProbeComplete()
    def progress(event):
        (output/'progress.json').write_bytes(canonical_bytes(event))
    with patch.object(candidate, 'correct_joints', solve), \
         patch('autospine_workbench.automation.motion_target_pose.final_times', capture):
        try:
            build(files, character, plan, progress)
        except ProbeComplete:
            return
    raise ValueError('probe_did_not_reach_final_validation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state_root', 'request', 'output'):parser.add_argument(name, type=Path)
    args = parser.parse_args(); run(args.state_root, args.request, args.output)
