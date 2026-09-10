"""Run a finite retained-weight repair policy before target admission."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from autospine_workbench.benchmark.mesh_storage import read_mesh_report, export_mesh
from autospine_workbench.asset.planning.sleeve_helper_review import render
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256


def needs_repair(report):
    return any(track['failed_ticks'] for row in report['records']
               for track in row.get('tracks', []))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--state-root', type=Path, default=Path('workspace'))
    p.add_argument('--workspace', type=Path, default=Path('..'))
    p.add_argument('projects', nargs='+')
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    for project in args.projects:
        require_safe_token(project, 'project')
        page = (args.input / project / 'index.html').read_text(encoding='utf-8')
        match = re.search(r'href="([a-f0-9]{64})\.json"', page)
        if not match:
            raise ValueError('sleeve_repair_source')
        sha = match[1]
        source = read_mesh_report(args.state_root, 'project-component-partitions', sha)
        if (source['schema'] != 'autospine.sleeve-motion-envelope/v1'
                or source['project_id'] != project or source['authority'] != 'none'
                or source['production_authorized'] is not False):
            raise ValueError('sleeve_repair_source')
        # First preserve the minimum allocation. Only remaining failures receive
        # explicit headroom inside the already established 50% forearm cap.
        for headroom in (0., .5):
            if not needs_repair(source):
                break
            destination = args.output / project / f'trial-{headroom:g}'
            result = subprocess.run([
                sys.executable, str(repo / 'tools/solve-retained-sleeve.py'),
                '--source', sha, '--output', str(destination),
                '--state-root', str(args.state_root), '--workspace', str(args.workspace),
                '--edge-budget', '--smooth-seed', '--blend-backtrack', '--reviewed-domain',
                '--trial-passes', '3', '--budget-headroom', str(headroom),
            ], env=dict(os.environ), check=True, capture_output=True, text=True, timeout=1500)
            print(result.stdout, end='', flush=True)
            addresses = re.findall(r'(?m)^([a-f0-9]{64})\s*$', result.stdout)
            if len(addresses) != 1:
                raise ValueError('sleeve_repair_result')
            updated = read_mesh_report(args.state_root, 'project-component-partitions', addresses[0])
            if updated['source_sha256'] != sha or updated['project_id'] != project:
                raise ValueError('sleeve_repair_result')
            sha, source = addresses[0], updated
        if canonical_sha256(source) != sha:
            raise ValueError('sleeve_repair_identity')
        output = args.output / project
        output.mkdir(parents=True, exist_ok=True)
        export_mesh(output / (sha + '.json'), source)
        (output / 'index.html').write_text(render(source).replace(
            '<main>', f'<a href="{sha}.json">完整工件</a><main>'), encoding='utf-8')


if __name__ == '__main__':
    main()
