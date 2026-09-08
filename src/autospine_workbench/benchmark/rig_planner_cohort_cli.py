"""Full-source cohort gate and content-addressed strategy summary."""
import argparse
from pathlib import Path
from .artifacts import read_input, read_report, publish_report, export_document
from .rig_planner_cli import read_plan
from .rig_planner_cohort import summarize, render
from .mapping_cli import export_html
from ..resolved_project import canonical_sha256


def read_cohort(state, manifest, workspace, digest):
    doc = read_report(state, manifest['dataset_id'], 'rig-plan-cohorts-v1', digest)
    entries = []
    for row in doc['characters']:
        plan = read_plan(state, manifest, workspace, row['plan_sha256'])
        bindings = read_report(state, manifest['dataset_id'], 'layer-binding-candidates-v2',
                               plan['source_bindings_sha256'])
        entries.append((row['label'], plan, [r['layer_id'] for r in bindings['bindings']]))
    if summarize(entries) != doc:
        raise ValueError('planner_cohort_replay_mismatch')
    return doc


def main():
    parser = argparse.ArgumentParser(description='Compare complete rig plans from the same profile')
    parser.add_argument('--plan', type=Path, action='append', required=True)
    for key in ('manifest', 'workspace', 'output', 'html'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args(); manifest = read_input(args.manifest); entries = []
    for path in args.plan:
        plan = read_plan(args.state_root, manifest, args.workspace, canonical_sha256(read_input(path)))
        bindings = read_report(args.state_root, manifest['dataset_id'], 'layer-binding-candidates-v2',
                               plan['source_bindings_sha256'])
        entries.append((path.parent.name, plan, [r['layer_id'] for r in bindings['bindings']]))
    doc = summarize(entries)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'rig-plan-cohorts-v1', doc)
    export_document(args.output, doc); export_html(args.html, render(doc))
    print(digest)


if __name__ == '__main__':
    main()
