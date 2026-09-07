"""Development-only alpha contacts without inferred anatomical authorization."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input, read_report
from .mapping_cli import export_html
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('probe-contacts', help='Inspect raw layer pair alpha contacts')
    for name in ('manifest', 'evidence', 'workspace', 'html'):
        cmd.add_argument('--' + name, type=Path, required=True)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--output', type=Path)


def read_contact_probe(state_root, manifest, digest, *, workspace):
    from .contact_probe import MAX_BYTES, validate_contact_probe

    doc = read_report(state_root, manifest['dataset_id'], 'contact-probes', digest)
    candidate = read_semantic_candidate(state_root, manifest, doc['candidate_sha256'])
    evidence = read_report(state_root, manifest['dataset_id'], 'semantic-evidence', candidate['evidence_sha256'])
    fresh, _, _, images = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'],
                                             max_layer_bytes=MAX_BYTES)
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('benchmark_contact_candidate_mismatch')
    return validate_contact_probe(candidate, images, doc)


def execute(args):
    from .contact_probe import MAX_BYTES, build_contact_probe
    from .contact_probe_view import render_contact_probe

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, images = load_semantic_inputs(manifest, evidence, args.workspace, args.character,
                                                             max_layer_bytes=MAX_BYTES)
    probe = build_contact_probe(candidate, images)
    html = render_contact_probe(candidate, probe, composite, images)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'contact-probes', probe)
    read_contact_probe(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return probe, 'contact-probes', manifest['dataset_id'], 0
