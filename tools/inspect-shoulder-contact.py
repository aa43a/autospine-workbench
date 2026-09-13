"""Measure source-alpha shoulder overlap without changing candidate authority."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_contact import source_image


def inspect(files):
    document = json.loads(files['skeleton.json'])
    manifest = json.loads(files['character-manifest.json'])
    positions, pose = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    bones = {b['name']: b for b in document['bones']}
    torso = []
    for row in manifest['layers']:
        if row['name'] in ('topwear', 'topwear-front') and row['state'] == 'rigid_reviewed':
            for region in row['regions']:
                im, origin = source_image(files, document, positions, region['region_id'])
                torso.append((im.getchannel('A'), origin))
    result = []
    for row in manifest['layers']:
        if row['name'] not in ('handwear-l', 'handwear-r'):
            continue
        side = row['name'][-1]
        root = pose['upperarm_' + side][:2]
        length = bones['upperarm_' + side]['length']
        if not math.isfinite(length) or length <= 0:
            raise ValueError('shoulder_length_invalid')
        for region in row['regions']:
            slot = region['region_id']
            im, origin = source_image(files, document, positions, slot)
            alpha = im.getchannel('A')
            contact = []; proximal = 0
            for y in range(im.height):
                for x in range(im.width):
                    world = (origin[0]+x, origin[1]-y)
                    if math.dist(world, root) > length*.65 or alpha.getpixel((x, y)) < 8:
                        continue
                    proximal += 1
                    if any(0 <= world[0]-o[0] < a.width and 0 <= o[1]-world[1] < a.height
                           and a.getpixel((world[0]-o[0], o[1]-world[1])) >= 8 for a, o in torso):
                        contact.append(world)
            bounds = None if not contact else [min(p[0] for p in contact), min(p[1] for p in contact),
                                               max(p[0] for p in contact), max(p[1] for p in contact)]
            result.append(dict(slot=slot, shoulder=list(root), upperarm_length=length,
                               proximal_pixels=proximal, overlap_pixels=len(contact),
                               overlap_bounds=bounds,
                               reason_code='contact_observed' if contact else 'shoulder_contact_missing'))
    return dict(authority='none', alpha_threshold=8, radius_upperarm_ratio=.65,
                scope='setup_source_alpha_only', regions=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(AnimatedStore(args.state_root).read(args.character))
    report['source_character_sha256'] = args.character
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
