"""Exact source replay and independently addressed area diagnostics."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.mesh_area import build_area_report, validate_area_report
from .artifacts import read_input, read_report
from .mesh_candidate_cli import inputs, read_mesh_candidate
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('screen-mesh-area', help='Locate excessive area loss in weighted meshes')
    for name in ('manifest', 'workspace', 'mesh', 'html'):
        cmd.add_argument('--'+name, type=Path, required=True)
    cmd.add_argument('--output', type=Path)


def sources(state, manifest, digest, workspace):
    mesh = read_mesh_candidate(state, manifest, digest, workspace=workspace)
    _, _, skeleton, _, _, _, _ = inputs(state, manifest, mesh['source_draft_sha256'], workspace)
    return mesh, skeleton


def read_area_report(state, manifest, digest, *, workspace):
    doc = read_report(state, manifest['dataset_id'], 'mesh-area-reports', digest)
    mesh, skeleton = sources(state, manifest, doc['source_mesh_sha256'], workspace)
    return validate_area_report(mesh, skeleton, doc)


def execute(args):
    from .mesh_area_view import render_area
    manifest = read_input(args.manifest)
    mesh, skeleton = sources(args.state_root, manifest, canonical_sha256(read_input(args.mesh)), args.workspace)
    doc = build_area_report(mesh, skeleton)
    export_html(args.html, render_area(mesh, skeleton, doc))
    return doc, 'mesh-area-reports', manifest['dataset_id'], 0
