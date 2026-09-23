"""Compare browser-exported pose previews with the production patch compiler."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.pose_geometry_patch import compile_patch


def check(editor, capture):
    scene = json.loads((editor/'scene.json').read_bytes())
    config = json.loads((editor/'editor-config.json').read_bytes())
    request = json.loads((capture/'request.json').read_bytes())
    if scene['artifact_sha256'] != config['artifact']:
        raise ValueError('preview_artifact_mismatch')
    document, report = compile_patch(scene['skeleton'], request)
    frames = []
    for frame in json.loads((capture/'interpolation.json').read_bytes()):
        if frame['artifact'] != config['artifact']:
            raise ValueError('preview_frame_artifact_mismatch')
        world = sample(document, request['animation'], frame['time'])[0][request['slot']]
        error = max(math.dist(a, b) for a, b in zip(world, frame['points'], strict=True))
        if error >= .001:
            raise ValueError('preview_compiler_mismatch')
        frames.append(dict(time=frame['time'], maximum_error_px=error))
    if len(frames) < 3:
        raise ValueError('preview_insufficient_samples')
    return dict(passed=True, artifact=config['artifact'], frames=frames,
                sampled_geometry_passed=report['sampled_geometry_passed'],
                scope='preview_compilation_fidelity_not_shape_acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('editor', type=Path)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    result = check(args.editor, args.capture)
    (args.capture/'compiler-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
