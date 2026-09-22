"""Compare fresh character validation with legacy versus history-only route guards."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs


def run(project, job):
    projects = ProjectStore(Path('..').resolve(), Path('workspace').resolve())
    sleeves = SleeveWebJobs(projects)
    characters = CharacterJobs(projects, sleeves)
    rows = []
    try:
        for mode in ('legacy', 'history', 'history', 'legacy'):
            guard = (lambda p: sleeves.overview(p).get('job') is not None) if mode == 'legacy' else sleeves.has_job
            with patch.object(sleeves, 'has_job', side_effect=guard):
                start = perf_counter()
                value = characters.get(project, job)
                rows.append(dict(mode=mode, seconds=perf_counter()-start,
                    status=value['status'], artifact_sha256=value.get('artifact_sha256')))
        if len({(r['status'], r['artifact_sha256']) for r in rows}) != 1:
            raise ValueError('validation_result_changed')
        return dict(project_id=project, job_id=job, samples=rows,
                    scope='fresh_character_get_not_http_submission_or_animation_quality')
    finally:
        characters.close()
        sleeves.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('job'); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = run(args.project, args.job)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
