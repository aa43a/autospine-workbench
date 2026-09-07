"""Inspect contact ambiguity while retaining all original geometric evidence."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input, read_report
from .contact_probe_cli import read_contact_probe
from .mapping_cli import export_html
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('screen-contacts', help='Screen clothing contact hypotheses without assigning joints')
    for name in ('manifest', 'evidence', 'workspace', 'html'):
        cmd.add_argument('--' + name, type=Path, required=True)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--output', type=Path)


def read_contact_screen(state_root, manifest, digest, *, workspace):
    from .contact_screen import validate_contact_screen

    doc = read_report(state_root, manifest['dataset_id'], 'contact-screens', digest)
    probe = read_contact_probe(state_root, manifest, doc['probe_sha256'], workspace=workspace)
    candidate = read_semantic_candidate(state_root, manifest, doc['candidate_sha256'])
    return validate_contact_screen(candidate, probe, doc)


def execute(args):
    from .contact_probe import MAX_BYTES, build_contact_probe
    from .contact_screen import build_contact_screen
    from .contact_screen_view import render_contact_screen

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, images = load_semantic_inputs(
        manifest, evidence, args.workspace, args.character, max_layer_bytes=MAX_BYTES)
    probe = build_contact_probe(candidate, images)
    screen = build_contact_screen(candidate, probe)
    html = render_contact_screen(candidate, probe, screen, composite, images)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    publish_report(args.state_root, manifest['dataset_id'], 'contact-probes', probe)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'contact-screens', screen)
    read_contact_screen(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return screen, 'contact-screens', manifest['dataset_id'], 0
