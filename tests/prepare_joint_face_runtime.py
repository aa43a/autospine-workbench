"""Opt-in real three-character facial fixture for official Core/WebGL checks."""
import argparse
import base64
import json
from pathlib import Path

from autospine_workbench.targets.character43.joint_face import apply, defaults
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.runtime_storage_reference import stored_document

ROOTS = {'alice': '6e5c59db4ef072075b798efab12acf8ffdc883368a61a4bf3c1646305ef68b98',
         'huiye': '63caa7fe5f9f40a92ebcd57ef0b345d7dcd47e5ed3feae65a95fad18e770d51b',
         'hongmeiling': 'fadde972f148b353592aaeebf75df151b9ef57032efaacde1773ea5a8754d28c'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('output'); parser.add_argument('--template', action='store_true')
    args = parser.parse_args(); out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    for name, digest in ROOTS.items():
        folder = Path('workspace/builds/animated-preview-v1')/digest
        files = {n: (folder/n).read_bytes() for n in ['character-manifest.json', 'skeleton.atlas']}
        doc = json.loads((folder/'skeleton.json').read_bytes()); config = defaults(); config['enabled'] = True
        config['mouth']['template_enabled'] = args.template
        for group, fields in {'gaze': {'x': 1, 'y': -.5}, 'brows': {'lift': 1, 'tilt': .5},
                              'mouth': {'open': 1, 'wide': .5}, 'turn': {'yaw': 1, 'pitch': .5}}.items():
            config[group]['keys'] = [dict(time=0, **{k: 0 for k in fields}), dict(time=1, **fields),
                                     dict(time=2, **{k: 0 for k in fields})]
        result, updates, report = apply(files, doc, 'idle', config, [0, 1, 2])
        stored = stored_document(result)
        times = [0, .5, .572, .59, .608, .68, .713, 1, 1.57, 2]
        payload = dict(skeleton=result, atlas=updates.get('skeleton.atlas', files['skeleton.atlas']).decode(),
            animation='idle', source=digest, report=report,
            texture_updates={n: base64.b64encode(v).decode() for n, v in updates.items() if n.startswith('textures/')},
            samples=[dict(time=t, vertices=sample(stored, 'idle', t)[0]) for t in times])
        (out/(name+'.json')).write_text(json.dumps(payload), encoding='utf8')
        print(name, len(report['affected_slots']), report['missing'], len(report['sample_times']))


if __name__ == '__main__':
    main()
