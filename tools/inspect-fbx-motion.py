"""Run in Blender background mode: inspect one motion without altering its source.

blender --background --factory-startup --python tools/inspect-fbx-motion.py -- INPUT OUTPUT
The sampled world joints are evidence, not a reviewed rig or a MotionIR export.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from io_scene_fbx import parse_fbx


def inspect(source):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    tree, version = parse_fbx.parse(str(source))
    settings = next(e for e in tree.elems if e.id == b'GlobalSettings')
    properties = next(e for e in settings.elems if e.id == b'Properties70')
    wanted = {'TimeMode', 'CustomFrameRate', 'UnitScaleFactor',
              'UpAxis', 'UpAxisSign', 'FrontAxis', 'FrontAxisSign',
              'CoordAxis', 'CoordAxisSign'}
    metadata = {e.props[0].decode(): e.props[4] for e in properties.elems
                if e.id == b'P' and e.props[0].decode() in wanted}
    if 'TimeMode' not in metadata:
        raise ValueError('source_time_mode_missing')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    result = bpy.ops.import_scene.fbx(filepath=str(source), use_anim=True,
                                      use_image_search=False)
    if 'FINISHED' not in result:
        raise ValueError('fbx_import_failed')
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(rigs) != 1 or not rigs[0].animation_data:
        raise ValueError('single_animated_armature_required')
    rig = rigs[0]
    action = rig.animation_data.action
    if action is None:
        raise ValueError('active_action_required')
    start, end = map(float, action.frame_range)
    if start != int(start) or end != int(end) or not 1 <= end-start <= 10000:
        raise ValueError('unsupported_frame_range')
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('invalid_imported_fps')
    samples = []
    for frame in range(int(start), int(end)+1):
        scene.frame_set(frame)
        joints = {b.name: list(rig.matrix_world @ b.head) for b in rig.pose.bones}
        if not all(math.isfinite(v) for p in joints.values() for v in p):
            raise ValueError('nonfinite_world_joint')
        samples.append({'frame': frame, 'seconds': (frame-start)/fps, 'joints': joints})
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError('source_changed_during_inspection')
    return {'schema': 'local.fbx-motion-inspection/v1', 'authority': 'none',
            'source_sha256': before, 'source': str(source), 'fbx_version': version,
            'blender_version': bpy.app.version_string, 'source_settings': metadata,
            'imported_fps': fps, 'frame_range': [start, end],
            'coordinate_space': 'blender_world', 'source_unchanged': True,
            'bones': [{'name': b.name, 'parent': b.parent.name if b.parent else None,
                       'rest_head': list(rig.matrix_world @ b.head_local)}
                      for b in rig.data.bones], 'samples': samples,
            'limitations': ['not_motion_ir', 'no_contact_or_loop_approval',
                            'no_runtime_validation', 'integer_imported_frame_sampling']}


if __name__ == '__main__':
    source, output = map(Path, sys.argv[sys.argv.index('--')+1:])
    report = inspect(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('source_sha256', 'source_settings',
                                            'imported_fps', 'frame_range')}))
