"""Build an isolated full-character transverse candidate and check official CPU FK."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_candidate import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def run(args):
    source = json.loads((args.source/'report.json').read_bytes())
    if args.verify_existing:
        fixture = json.loads((args.output/'numeric-fixture.json').read_bytes())
        digest = Path(fixture['reference_bundle']).name
        if fixture['source_candidate'] != source['candidate_bundle_sha256']:
            raise ValueError('transverse_probe_source_changed')
        store = AnimatedStore(args.output/'isolated-store')
        if Path(fixture['reference_bundle']).resolve() != (store.root/digest).resolve():
            raise ValueError('transverse_probe_store_mismatch')
        output = store.read(digest)
        return finish(args, source, output, json.loads(output['motion-transverse.json']), digest)
    args.output.mkdir(parents=True, exist_ok=False)
    files = AnimatedStore(args.source/'isolated-store').read(source['candidate_bundle_sha256'])
    last = None
    def progress(event):
        nonlocal last
        if last != event['stage']:
            print(json.dumps(event), flush=True); last = event['stage']
    output, report = build(files, args.slots, on_progress=progress)
    store = AnimatedStore(args.output/'isolated-store'); digest = store.publish(output)
    assert store.read(digest) == output
    finish(args, source, output, report, digest)


def finish(args, source, output, report, digest):
    store = AnimatedStore(args.output/'isolated-store')
    if list(report['transverse']['slots']) != args.slots:
        raise ValueError('transverse_probe_slots_changed')
    (args.output/'skeleton.json').write_bytes(output['skeleton.json'])
    document = json.loads(output['skeleton.json']); name = 'external-motion'
    end = read(output)['animations'][name][-1]['time']; times = [f32(end*i/128) for i in range(129)]
    fixture = dict(source_candidate=source['candidate_bundle_sha256'],
        runtime_sha256=sha256(args.runtime.read_bytes()).hexdigest(),
        skeleton_sha256=sha256(output['skeleton.json']).hexdigest(), skeleton=document,
        atlas=output['skeleton.atlas'].decode(), animation=name,
        samples=[dict(time=t, vertices={s: p for s, p in sample(document, name, t)[0].items()
                                      if s in args.slots}) for t in times],
        reference_bundle=str((store.root/digest).resolve()), reference_frames=report['sample_count'])
    path = args.output/'numeric-fixture.json'; path.write_bytes(canonical_bytes(fixture))
    checked = subprocess.run([str(args.node), str(Path(__file__).with_name('check-corrective-numeric.mjs')),
        str(path), str(args.runtime)], capture_output=True, text=True, timeout=120)
    if checked.returncode:
        (args.output/'numeric-failure.txt').write_text(checked.stdout+checked.stderr, encoding='utf-8')
        checked.check_returncode()
    numeric = json.loads(checked.stdout)
    (args.output/'official-numeric.json').write_bytes(canonical_bytes(numeric))
    summary = dict(candidate_bundle_sha256=digest, parent_artifact=source['candidate_bundle_sha256'],
        skeleton_sha256=fixture['skeleton_sha256'], slots=args.slots, official_cpu=numeric,
        sample_count=report['sample_count'], before=report['parent_geometry'], after=report['geometry'],
        transverse=report['transverse'], contact_status=report['contact_status'],
        joint_correction_passed=all(not row['solver']['refinement'][-1]['check']['failures']
            and row['fixed_area_blocker'] is None for row in report['joint_corrections']),
        fixed_area_blocked_slots=[r['slot'] for r in report['joint_corrections'] if r['fixed_area_blocker']],
        gpu_status='not_run', visual_status='not_reviewed', selected=False, authority='none')
    (args.output/'report.json').write_bytes(canonical_bytes(summary))
    print(json.dumps(dict(stage='complete', candidate=digest, cpu_error_px=numeric['maximum_error_px'],
        geometry_passed=summary['after']['passed'], joint_correction_passed=summary['joint_correction_passed'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'node', 'runtime'):parser.add_argument(name, type=Path)
    parser.add_argument('slots', nargs='+')
    parser.add_argument('--verify-existing', action='store_true')
    run(parser.parse_args())
