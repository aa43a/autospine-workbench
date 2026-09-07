"""Match pinned detector observations to contact evidence, without adoption."""
from pathlib import Path

from .artifacts import publish_report, read_input, read_report
from .contact_screen_cli import read_contact_screen
from .mapping_cli import export_html
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('match-pose-contacts', help='Match source-bound pose anchors to distinct contact regions')
    for name in ('manifest', 'evidence', 'workspace', 'html'):
        cmd.add_argument('--' + name, type=Path, required=True)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--pose-observations', type=Path)
    cmd.add_argument('--output', type=Path)


def read_pose_contact_match(state_root, manifest, digest, *, workspace):
    from .pose_contact_match import validate_pose_contact_match
    from .pose_source import read_pose

    dataset = manifest['dataset_id']
    doc = read_report(state_root, dataset, 'pose-contact-matches', digest)
    screen = read_contact_screen(state_root, manifest, doc['screen_sha256'], workspace=workspace)
    probe = read_report(state_root, dataset, 'contact-probes', doc['probe_sha256'])
    candidate = read_semantic_candidate(state_root, manifest, doc['candidate_sha256'])
    pose = read_pose(state_root, candidate, doc['pose_sha256']) if doc['pose_sha256'] is not None else None
    return validate_pose_contact_match(candidate, probe, screen, pose, doc)


def ingest_selected_runner(args, candidate, evidence):
    from ..runners.pose import PoseRunnerRequest, CanonicalPoseFileImporter
    from .pose_source import ingest_pose

    if args.pose_observations is None:
        return None
    record = next(row for row in evidence['characters'] if row['character_id'] == candidate['character_id'])
    request = PoseRunnerRequest(candidate['character_id'], candidate['composite_sha256'], tuple(candidate['canvas']),
                                Path(args.workspace) / record['outputs']['composite']['path'])
    produced = CanonicalPoseFileImporter(args.pose_observations).produce(request)
    return ingest_pose(args.state_root, candidate, produced)


def execute(args):
    from .contact_probe import MAX_BYTES, build_contact_probe
    from .contact_screen import build_contact_screen
    from .pose_contact_match import build_pose_contact_match
    from .pose_contact_view import render_pose_contact_match

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, images = load_semantic_inputs(
        manifest, evidence, args.workspace, args.character, max_layer_bytes=MAX_BYTES)
    probe = build_contact_probe(candidate, images)
    screen = build_contact_screen(candidate, probe)
    pose = ingest_selected_runner(args, candidate, evidence)
    doc = build_pose_contact_match(candidate, probe, screen, pose)
    html = render_pose_contact_match(candidate, probe, screen, pose, doc, composite, images)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    for kind, value in (('contact-probes', probe), ('contact-screens', screen), ('pose-contact-matches', doc)):
        digest = publish_report(args.state_root, manifest['dataset_id'], kind, value)
    read_pose_contact_match(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return doc, 'pose-contact-matches', manifest['dataset_id'], 0
