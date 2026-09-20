"""Fresh official captures for exact original/partitioned motion representations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.runtime_storage_reference import build as storage
from autospine_workbench.targets.character43.framebuffer_equivalence import compare


def prepare(partition, output):
    report = json.loads((partition/'report.json').read_bytes())
    raw = (partition/'skeleton.json').read_bytes()
    if sha256(raw).hexdigest() != report['skeleton_sha256']:
        raise ValueError('partition_skeleton_identity')
    original = AnimatedStore(Path('workspace')).read(report['source_artifact_sha256'])
    depth = json.loads(original['motion-depth.json'])
    ticks = sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    if not ticks or len(ticks) > 512:
        raise ValueError('partition_capture_frame_bound')
    times = sorted({t/1e6 for t in ticks} | {(a+b)/2e6 for a,b in zip(ticks,ticks[1:])})
    store = AnimatedStore(output/'isolated-store')
    captures = []
    for name, skeleton in [('original', original['skeleton.json']), ('partitioned', raw)]:
        document = json.loads(skeleton)
        frames = [dict(time=t, vertices=sample(document, 'external-motion', t)[0]) for t in times]
        files = {n: value for n,value in original.items() if n.endswith('.png') or n == 'skeleton.atlas'}
        files.update({'skeleton.json': skeleton, 'character-manifest.json': canonical_bytes(dict(
            authority='none', production_authorized=False, source_artifact_sha256=report['source_artifact_sha256'],
            scope='isolated_partition_render_equivalence'))})
        files = write(files, dict(skeleton_sha256=sha256(skeleton).hexdigest(),
                                 animations={'external-motion': frames}))
        digest = store.publish(files)
        storage_path = output/(name+'-storage.json')
        storage_path.write_bytes(canonical_bytes(storage(files)))
        captures.append(dict(name=name, bundle=str((store.root/digest).resolve()),
                             bundle_sha256=digest, storage=str(storage_path.resolve())))
    return captures


def run(partition, output):
    output.mkdir(parents=True, exist_ok=True)
    captures = prepare(partition, output)
    options = discover(Path.cwd().parent)
    if not options:
        raise ValueError('official_capture_environment_missing')
    (output/'capture-inputs.json').write_bytes(canonical_bytes(captures))
    for row in captures:
        command = ['node', 'tools/capture-character-runtime.mjs', row['bundle'], str(output/row['name']),
                   options[1], options[3], '1', '{}', row['storage']]
        with (output/(row['name']+'.log')).open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=300,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('partition_capture_failed_'+row['name'])
        print(json.dumps(dict(captured=row['name'], bundle=row['bundle_sha256'])), flush=True)
    equivalence = compare(output/'original', output/'partitioned')
    (output/'equivalence.json').write_bytes(canonical_bytes(equivalence))
    print(json.dumps(dict(equivalent=equivalence['passed'], frames=len(equivalence['frames']))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('partition', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.partition, args.output)
