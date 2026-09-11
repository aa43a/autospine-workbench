"""Build and replay a source-bound ordinary sleeve discrete deformation candidate."""
import argparse
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build
from autospine_workbench.asset.planning.ordinary_sleeve_deform_review import render
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--repair', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--state-root', default=Path('workspace'), type=Path)
    parser.add_argument('--workspace', default=Path('..'), type=Path)
    args = parser.parse_args()
    require_safe_token(args.project, 'project')
    read = lambda sha: read_mesh_report(args.state_root, 'project-component-partitions', sha)
    repair = read(args.repair)
    if repair['project_id'] != args.project:
        raise ValueError('ordinary_deform_project_mismatch')
    source, draft = read(repair['source_sha256']), read(repair['draft_sha256'])
    store = ProjectStore(args.workspace.resolve(), args.state_root.resolve())
    with load_inputs(store, args.project) as inputs:
        report = build(repair, source, draft, inputs.skeleton)
        html = render(report, repair=repair, source=source, draft=draft, skeleton=inputs.skeleton)
        inputs.assert_current()
        sha = publish_mesh_report(args.state_root, 'project-component-partitions', report)
        if read(sha) != report:
            raise ValueError('ordinary_deform_readback_mismatch')
        args.output.mkdir(parents=True, exist_ok=True)
        export_mesh(args.output/(sha+'.json'), report)
        (args.output/'index.html').write_text(html, encoding='utf-8')
        print(sha)


if __name__ == '__main__':
    main()
