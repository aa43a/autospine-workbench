"""Exact probe-to-mesh checks and optional official capture, in an isolated store."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.runtime_storage_reference import build as storage


def run(probe, output, capture=False):
    receipt = json.loads((probe/'report.json').read_bytes())
    document = json.loads((probe/'skeleton.json').read_bytes())
    if receipt['output_sha256'] != canonical_sha256(document):
        raise ValueError('source_pose_probe_identity')
    files = AnimatedStore(Path('workspace')).read(receipt['character_sha256'])
    original = json.loads(files['skeleton.json'])
    if {k:v for k,v in original.items() if k != 'animations'} != {k:v for k,v in document.items() if k != 'animations'}:
        raise ValueError('source_pose_rig_changed')
    animation, = document['animations']
    knots = sorted({k['time'] for tracks in document['animations'][animation]['bones'].values()
                    for keys in tracks.values() for k in keys})
    times = sorted(set(knots) | {(a+b)/2 for a,b in zip(knots,knots[1:])})
    if not 2 <= len(times) <= 2049:
        raise ValueError('source_pose_sample_limit')
    output.mkdir(parents=True, exist_ok=False)
    raw = canonical_bytes(document)
    frames = [dict(time=t, vertices=sample(document, animation, t)[0]) for t in times]
    isolated = {n:v for n,v in files.items() if n.endswith('.png') or n == 'skeleton.atlas'}
    isolated['skeleton.json'] = raw
    isolated['character-manifest.json'] = canonical_bytes(dict(authority='none',
        source_character_sha256=receipt['character_sha256'], source_identity=receipt['source_identity'],
        production_authorized=False, profile=receipt['profile']))
    isolated = write(isolated, dict(skeleton_sha256=sha256(raw).hexdigest(), animations={animation:frames}))
    setup = deepcopy(document); setup['animations'] = {animation:{'bones':{}}}
    qa = inspect(isolated, setup_vertices=sample(setup, animation, 0)[0])
    (output/'deformation.json').write_bytes(canonical_bytes(qa))
    store = AnimatedStore(output/'isolated-store'); digest = store.publish(isolated)
    report = dict(profile=receipt['profile'], probe_receipt_sha256=sha256((probe/'report.json').read_bytes()).hexdigest(),
        candidate_bundle_sha256=digest, skeleton_sha256=sha256(raw).hexdigest(),
        sampled_frames=len(times), geometry_passed=qa['passed'],
        failing_slots=[r for r in qa['records'] if not r['passed']],
        contact_status='not_evaluated', depth_status='not_evaluated', runtime_status='not_evaluated',
        authority='none', selected=False, production_authorized=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(stage='geometry',frames=len(times),failed_slots=len(report['failing_slots']))),flush=True)
    if capture:
        env = discover(Path.cwd().parent)
        if not env:
            raise ValueError('official_capture_environment_missing')
        reference = output/'runtime-storage.json'; reference.write_bytes(canonical_bytes(storage(isolated)))
        command = ['node','tools/capture-character-runtime.mjs',str((store.root/digest).resolve()),
            str((output/'runtime').resolve()),env[1],env[3],'32','{}',str(reference.resolve())]
        with (output/'capture.log').open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        report['runtime_status'] = 'capture_failed'
        if result.returncode == 0:
            actual = json.loads((output/'runtime/report.json').read_bytes())
            if actual['bundle_sha256'] != digest or [r['time'] for r in actual['results']] != times:
                raise ValueError('source_pose_capture_identity')
            report['runtime_status'] = 'passed' if actual['passed'] else 'failed'
            report['runtime_max_error_px'] = max(r['max_error_px'] for r in actual['results'])
        (output/'report.json').write_bytes(canonical_bytes(report))
        print(json.dumps(dict(stage='runtime',status=report['runtime_status'])),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();run(args.probe,args.output,args.capture)
