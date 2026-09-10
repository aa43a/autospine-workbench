"""Build a bounded ordinary-sleeve repair candidate and paired diagnostic timeline."""
import argparse
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build
from autospine_workbench.asset.planning.ordinary_sleeve_repair_review import render
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--source', required=True, help='Content address of sleeve-weights/v1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--workspace', type=Path, default=Path('..'))
    args = parser.parse_args()
    require_safe_token(args.project, 'project')
    read = lambda sha: read_mesh_report(args.state_root, 'project-component-partitions', sha)
    source = read(args.source)
    if source['project_id'] != args.project:
        raise ValueError('ordinary_sleeve_repair_project_mismatch')
    store = ProjectStore(args.workspace.resolve(), args.state_root.resolve())
    with load_inputs(store, args.project) as inputs:
        report = build(source, read(source['draft_sha256']), inputs.skeleton)
        inputs.assert_current()
        # Build already replays every trial. Verify immutable readback here;
        # independent consumers use the full-closure replay validator.
        sha = publish_mesh_report(args.state_root, 'project-component-partitions', report)
        checked = read(sha)
        if canonical_sha256(checked) != canonical_sha256(report):
            raise ValueError('ordinary_sleeve_repair_readback_mismatch')
        args.output.mkdir(parents=True, exist_ok=True)
        export_mesh(args.output/(sha+'.json'), checked)
        (args.output/'index.html').write_text(render(checked), encoding='utf-8')
        print(sha)


if __name__ == '__main__':
    main()
