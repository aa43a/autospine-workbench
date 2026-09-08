"""Run with python -m autospine_workbench.benchmark.rig_planner_cli."""
import argparse
from pathlib import Path
from .artifacts import read_input, read_report, publish_report, export_document
from .layer_binding_cli import read_layer_binding_draft, read_layer_bindings
from .region_binding_cli import sources
from .mapping_cli import export_html
from .rig_planner_view import render
from ..asset.planning.rig_planner import build
from ..resolved_project import canonical_sha256


def replay(state, manifest, workspace, draft_sha, scope):
    draft = read_layer_binding_draft(state, manifest, draft_sha, workspace=workspace)
    bindings = read_layer_bindings(state, manifest, draft['source_bindings_sha256'], workspace=workspace)
    candidate, _, skeleton, composite, images = sources(
        state, manifest, bindings['source_skeleton_sha256'], workspace)
    return build(candidate, skeleton, bindings, draft, images, scope), candidate, composite, images


def read_plan(state, manifest, workspace, digest):
    doc = read_report(state, manifest['dataset_id'], 'rig-plans-v1', digest)
    fresh = replay(state, manifest, workspace, doc['source_draft_sha256'], doc['scope'])[0]
    if fresh != doc:
        raise ValueError('planner_replay_mismatch')
    return doc


def main():
    parser = argparse.ArgumentParser(description='Generate review-only rig strategies from existing binding candidates')
    for name in ('manifest', 'workspace', 'draft', 'html', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--focus-layer', action='append')
    args = parser.parse_args()
    manifest = read_input(args.manifest)
    doc, candidate, composite, images = replay(args.state_root, manifest, args.workspace,
        canonical_sha256(read_input(args.draft)), args.focus_layer)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'rig-plans-v1', doc)
    read_plan(args.state_root, manifest, args.workspace, digest)
    export_document(args.output, doc)
    export_html(args.html, render(doc, candidate, composite, images))
    print(digest)


if __name__ == '__main__':
    main()
