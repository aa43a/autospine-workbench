"""Generate source-bound pixel candidates for current registered projects."""
import argparse
from html import escape
from pathlib import Path

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.project_rig_plan import read_plan
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.artifacts import publish_report, read_report, export_document
from autospine_workbench.asset.planning.component_partitions import build, validate
from autospine_workbench.asset.planning.component_partition_review import render
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.asset.planning.component_ownership import template, validate as validate_draft
from autospine_workbench.benchmark.artifacts import read_input
from autospine_workbench.asset.planning.component_suggestions import build as suggest
from autospine_workbench.safe_input_files import read_real_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('..'))
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draft', type=Path, help='Validate and archive one supplied draft; never apply bindings')
    parser.add_argument('projects', nargs='+')
    args = parser.parse_args()
    if args.draft and len(args.projects) != 1:
        parser.error('--draft requires exactly one project')
    store = ProjectStore(args.workspace, args.state_root)
    links = []
    for project in args.projects:
        require_safe_token(project, 'Project')
        plan = read_plan(store, project)
        if plan['status'] != 'ready':
            raise ValueError('current_rig_plan_required')
        scope = {row['layer_id'] for row in plan['plan']['layers']
                 if row['strategy'] in ('weighted_mesh', 'partition_mesh', 'semantic_review')}
        output = args.output / project; output.mkdir(parents=True, exist_ok=True)
        entries = []
        with load_inputs(store, project) as source:
            if source.source_addresses['input_identity_sha256'] != plan['input_identity_sha256']:
                raise ValueError('partition_source_changed')
            for layer in source.candidate['layers']:
                if layer['layer_id'] not in scope:
                    continue
                raw = source.images[layer['layer_id']]
                candidate = build(layer, raw)
                document = dict(schema='autospine.project-component-partitions/v1', authority='none',
                                production_authorized=False, project_id=project,
                                source_addresses=source.source_addresses, source_plan_sha256=plan['plan_sha256'],
                                candidate=candidate)
                source.assert_current()
                digest = publish_report(args.state_root, 'project-component-partitions', 'candidates-v1', document)
                checked = read_report(args.state_root, 'project-component-partitions', 'candidates-v1', digest)
                validate(layer, raw, checked['candidate'])
                export_document(output / f'{digest}.json', checked)
                entries.append((layer, raw, candidate, digest))
            source.assert_current()
            draft = template(project, entries, source.source_addresses, plan['plan_sha256'], [b['id'] for b in source.skeleton['bones']])
            suggestions = suggest(entries, source.skeleton, source.bindings, draft['sources'])
            suggestion_sha = publish_report(args.state_root, 'project-component-partitions', 'ownership-suggestions-v1', suggestions)
            export_document(output / f'{suggestion_sha}.json', suggestions)
            print(f"{project}: {sum(r['status'] == 'suggested' for r in suggestions['records'])} suggested regions")
            if args.draft:
                draft = validate_draft(read_input(args.draft), draft)
                publish_report(args.state_root, 'project-component-partitions', 'ownership-drafts-v1', draft)
            source.assert_current()
            scene = dict(canvas=source.candidate['canvas'], bones=source.skeleton['bones'],
                         composite=read_real_file(Path(store.resolve_asset(project,'composite')),64 << 20,'composite'))
            source.assert_current()
        (output / 'index.html').write_text(render(project, entries, draft, suggestions, scene), encoding='utf-8')
        count = sum(len(row[2]['components']) for row in entries)
        residual = sum(row[2]['residual']['pixel_count'] for row in entries)
        print(f'{project}: {len(entries)} layers, {count} components, {residual} low-alpha residual pixels')
        links.append(f'<li><a href="{escape(project)}/index.html">{escape(project)} · {len(entries)} 层 · {count} 区域 · {residual} 残余像素</a></li>')
    (args.output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>像素分区候选</h1><p>归属未确定；未修改绑定决定或纹理。</p><ul>' + ''.join(links) + '</ul>', encoding='utf-8')


if __name__ == '__main__':
    main()
