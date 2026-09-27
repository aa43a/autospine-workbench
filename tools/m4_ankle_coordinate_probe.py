"""Compare root translation and isolated ancestor rotation effects without adoption."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def probe(files):
    document = json.loads(files['skeleton.json'])
    moving = json.loads(files['motion-moving-ankles.json'])
    motion = json.loads(files['motion-ir.json'])
    if moving['applied'] or canonical_sha256(document) != moving['input_skeleton_sha256']:
        raise ValueError('requires_unchanged_failed_input')
    if len(document['animations']) != 1:
        raise ValueError('ambiguous_animation')
    name = next(iter(document['animations']))
    tracks = document['animations'][name]['bones']
    reference = moving['final_check']['limit_px']/.01
    root = next(r for r in motion['tracks'] if r['target'] == 'humanoid.root' and r['property'] == 'translation')
    keys = [dict(time=k['tick']/motion['ticks_per_second'], vertices=[k['value'][0]*reference, -k['value'][1]*reference]) for k in root['keys']]
    translated = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in tracks['root']['translate']]
    times = sorted({k['time'] for k in keys} | {k['time'] for k in translated})
    mismatch = max(math.dist(interpolate(keys, t, 'vertices'), interpolate(translated, t, 'vertices')) for t in times)
    bones = {b['name']: b for b in document['bones']}
    ancestors = set()
    for side in ('l', 'r'):
        bone = bones['thigh_'+side].get('parent')
        while bone:
            ancestors.add(bone)
            bone = bones[bone].get('parent')
    variants = {'unchanged': document}
    for bone in sorted(ancestors):
        if tracks.get(bone, {}).get('rotate'):
            changed = deepcopy(document)
            changed['animations'][name]['bones'][bone].pop('rotate')
            variants['without_rotation_'+bone] = changed
    targets = [[dict(time=r['time'], vertices=r['targets'][i]) for r in moving['trajectory']] for i in (0, 1)]
    rows = []
    for t in (0., .033333, .066667, .1, .15):
        for label, changed in variants.items():
            pose = matrices(changed, name, t)
            rows.append(dict(time=t, variant=label, feet={side: dict(
                position=list(pose['foot_'+side][4:6]), hip=list(pose['thigh_'+side][4:6]),
                error_px=math.dist(pose['foot_'+side][4:6], interpolate(targets[i], t, 'vertices')))
                for i, side in enumerate(('l', 'r'))}))
    return dict(schema='autospine.ankle-coordinate-probe/v1', selected=False, authority='none',
                root_translation_maximum_mismatch_px=mismatch, source_reference=moving['source_observation']['source_reference_length'],
                target_reference=reference, root_setup=bones['root'], rows=rows,
                scope='isolated_channel_ablation_not_repair_or_additive_causal_proof')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = probe(AnimatedStore(Path('workspace')).read(args.artifact))
    result['artifact_sha256'] = args.artifact
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
