"""One technical chain: source pose, contact matching, constraints, skeleton."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input, read_report
from .mapping_cli import export_html
from .pose_contact_cli import read_pose_contact_match, ingest_selected_runner
from .pose_source import read_pose
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('build-r2a', help='Build an unapproved canonical skeleton from pinned pose observations')
    for name in ('manifest', 'evidence', 'workspace', 'html'):
        cmd.add_argument('--' + name, required=True, type=Path)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--pose-observations', type=Path)
    cmd.add_argument('--output', type=Path)


def _report(candidate, match, optimized, skeleton):
    return {'schema': 'autospine.benchmark-r2a/v1', 'authority': 'none', 'diagnostic_only': True,
            'candidate_sha256': canonical_sha256(candidate), 'match_sha256': canonical_sha256(match),
            'optimization_sha256': canonical_sha256(optimized), 'skeleton_sha256': canonical_sha256(skeleton),
            'status': skeleton['status'], 'bone_count': len(skeleton['bones']),
            'reason_codes': skeleton['reason_codes'], 'production_authorized': False,
            'accuracy_evaluated': False, 'runtime_verified': False}


def read_r2a(state_root, manifest, digest, *, workspace):
    from ..asset.joints.optimizer import validate_joint_optimization
    from ..asset.joints.skeleton import validate_canonical_skeleton

    dataset = manifest['dataset_id']
    doc = read_report(state_root, dataset, 'r2a-runs', digest)
    match = read_pose_contact_match(state_root, manifest, doc['match_sha256'], workspace=workspace)
    candidate = read_semantic_candidate(state_root, manifest, doc['candidate_sha256'])
    pose = read_pose(state_root, candidate, match['pose_sha256']) if match['pose_sha256'] else None
    optimized = read_report(state_root, dataset, 'joint-optimizations', doc['optimization_sha256'])
    validate_joint_optimization(candidate, pose, match, optimized)
    skeleton = read_report(state_root, dataset, 'canonical-skeleton-candidates', doc['skeleton_sha256'])
    validate_canonical_skeleton(candidate, optimized, skeleton)
    expected = _report(candidate, match, optimized, skeleton)
    if canonical_sha256(doc) != canonical_sha256(expected):
        raise ValueError('benchmark_r2a_report_mismatch')
    return expected


def execute(args):
    from ..asset.joints.optimizer import optimize_joints
    from ..asset.joints.skeleton import build_canonical_skeleton
    from .contact_probe import MAX_BYTES, build_contact_probe
    from .contact_screen import build_contact_screen
    from .pose_contact_match import build_pose_contact_match
    from .r2a_view import render_r2a

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, images = load_semantic_inputs(
        manifest, evidence, args.workspace, args.character, max_layer_bytes=MAX_BYTES)
    pose = ingest_selected_runner(args, candidate, evidence)
    probe = build_contact_probe(candidate, images)
    screen = build_contact_screen(candidate, probe)
    match = build_pose_contact_match(candidate, probe, screen, pose)
    optimized = optimize_joints(candidate, pose, match)
    skeleton = build_canonical_skeleton(candidate, optimized)
    report = _report(candidate, match, optimized, skeleton)
    html = render_r2a(candidate, optimized, skeleton, report, composite)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    for kind, doc in (('contact-probes', probe), ('contact-screens', screen), ('pose-contact-matches', match),
                      ('joint-optimizations', optimized), ('canonical-skeleton-candidates', skeleton), ('r2a-runs', report)):
        digest = publish_report(args.state_root, manifest['dataset_id'], kind, doc)
    read_r2a(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return report, 'r2a-runs', manifest['dataset_id'], 0 if skeleton['status'] == 'candidate_requires_review' else 2
