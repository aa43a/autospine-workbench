"""Blender-only FBX to BVH bridge; preserve inspection evidence beside the export."""
import hashlib
import json
from pathlib import Path
import runpy
import re
import sys

import bpy
from io_anim_bvh import export_bvh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.bvh_parser import parse_bvh


def export(source, output, *, root_only=False):
    inspect = runpy.run_path(str(Path(__file__).with_name('inspect-fbx-motion.py')))['inspect']
    evidence = inspect(source)
    rig, = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    # Keep local animation channels and units together. Applying object scale alone
    # scales rest bones but not animated translation channels.
    object_matrix = [list(row) for row in rig.matrix_world]
    output.parent.mkdir(parents=True, exist_ok=True)
    start, end = map(int, evidence['frame_range'])
    export_bvh.save(bpy.context, filepath=str(output), frame_start=start, frame_end=end,
                    global_scale=1.0, rotate_mode='XYZ', root_transform_only=root_only,
                    sort_children_by_names=True)
    text = output.read_text(encoding='utf-8')
    text, count = re.subn(r'(?m)^Frame Time: .+$',
                         f"Frame Time: {1/evidence['imported_fps']:.17g}", text)
    if count != 1:
        raise ValueError('bvh_frame_time_missing')
    # Blender writes absolute local positions; our declared BVH convention adds
    # translation channels to OFFSET. Convert each position to that delta.
    parsed = parse_bvh(text.encode('utf-8'))
    rows = []
    for frame in parsed.frames:
        values, cursor = list(frame), 0
        for joint in parsed.joints:
            for channel in joint.channels:
                if channel.endswith('position'):
                    values[cursor] -= joint.offset['XYZ'.index(channel[0])]
                cursor += 1
        rows.append(' '.join(format(v, '.17g') for v in values))
    text = text[:text.index('Frame Time:')] + f"Frame Time: {1/evidence['imported_fps']:.17g}\n"
    text += '\n'.join(rows) + '\n'
    output.write_text(text, encoding='utf-8')
    evidence['bridge'] = {'profile': 'blender-bvh-local-v1',
                          'root_translation_only': root_only,
                          'local_to_blender_world': object_matrix,
                          'bvh_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                          'verification': 'required', 'rotation_order': 'XYZ'}
    output.with_suffix('.inspection.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root-only', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    export(args.source, args.output, root_only=args.root_only)
