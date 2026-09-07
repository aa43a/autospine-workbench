"""Run the pinned CPU model in an explicitly installed isolated environment."""
import argparse
import hashlib
import json
from pathlib import Path

from ...benchmark.artifacts import export_document
from ...png_rgba import decode_rgba_png
from ...resolved_project import canonical_sha256
from ...safe_input_files import read_real_file, strict_json_object
from .base import PoseRunnerRequest
from .dwpose import DWPoseOnnxRunner


def resolve_source(args):
    if args.character is not None:
        if args.image is not None or args.project is not None or any(
                value is None for value in (args.manifest, args.evidence, args.workspace)):
            raise ValueError('dwpose_benchmark_source_arguments_invalid')
        from ...benchmark.artifacts import read_input
        from ...benchmark.semantic_cli import load_semantic_inputs
        manifest, evidence = read_input(args.manifest), read_input(args.evidence)
        candidate, *_ = load_semantic_inputs(manifest, evidence, args.workspace, args.character)
        record = next(row for row in evidence['characters'] if row['character_id'] == candidate['character_id'])
        return PoseRunnerRequest(candidate['character_id'], candidate['composite_sha256'], tuple(candidate['canvas']),
                                 args.workspace / record['outputs']['composite']['path'])
    if args.image is None or args.project is None or any(
            value is not None for value in (args.manifest, args.evidence, args.workspace)):
        raise ValueError('dwpose_source_arguments_invalid')
    raw = read_real_file(args.image, 128 * 1024 * 1024, 'Pose source image')
    image = decode_rgba_png(raw)
    return PoseRunnerRequest(args.project, hashlib.sha256(raw).hexdigest(), (image.width, image.height), args.image)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'state-root', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('image', 'manifest', 'evidence', 'workspace'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--project')
    parser.add_argument('--character')
    parser.add_argument('--mirror-state', choices=('unknown', 'mirrored', 'not_mirrored'), default='unknown')
    parser.add_argument('--view', choices=('unknown', 'front', 'three_quarter', 'back', 'left_profile', 'right_profile'), default='unknown')
    args = parser.parse_args(argv)
    try:
        request = resolve_source(args)
        runner = DWPoseOnnxRunner(args.model, args.state_root, args.mirror_state, args.view)
        result = runner.produce(request)
        document = strict_json_object(read_real_file(result, 1_000_000, 'Pose result'), 'Pose result')
        export_document(args.output, document)
        print(json.dumps({'status': 'succeeded', 'pose_sha256': canonical_sha256(document), 'authority': 'none'}))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({'status': 'failed', 'reason_code': str(exc), 'authority': 'none'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
