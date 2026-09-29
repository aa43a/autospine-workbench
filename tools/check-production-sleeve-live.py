"""Replay saved sleeve inputs through production preparation in isolated job folders.

This is a real build, not a new independent material or human acceptance.
Existing source preparation and binding decisions are prerequisites, not measured work.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.production_driver import ProductionDriver
from autospine_workbench.automation.production_journal import ProductionJournal
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('project')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    projects = ProjectStore(Path('..'), state_root=Path('workspace'))
    sleeves = SleeveWebJobs(projects)
    sleeves.root = output/'sleeve-jobs'
    sleeves.output = output/'sleeve-output'
    characters = CharacterJobs(projects, sleeves)
    characters.root = output/'character-jobs'
    driver = ProductionDriver(SimpleNamespace(projects=projects, character_manager=lambda:characters))
    journal = ProductionJournal(output/'production')
    source = projects.get_project(args.project)['resolved']['sha256']
    value = journal.create(dict(project_id=args.project, character_job_id=None,
                                character_sha256=None, resolved_sha256=source))
    for stage in ('source','bindings'):
        value['stages'][stage].update(status='succeeded', basis='existing_saved_inputs')
    value = journal.append(value, 'existing_prerequisites')
    run = value['run_id']
    def read():
        return journal.read(run)
    def write(change, event):
        current = read(); change(current)
        journal.append(current, event)
        print(json.dumps(dict(event=event, run_id=run)), flush=True)
    start = time.monotonic()
    try:
        completed = driver.prepare(read, write, lambda:False)
        current = read()
        result, files = characters.verified_snapshot(args.project, current['stages']['character']['job_id'])
        report = dict(completed=completed, project=args.project, run_id=run,
            elapsed_seconds=time.monotonic()-start, stages=current['stages'],
            character_artifact_sha256=result['artifact_sha256'],
            files=len(files), human_acceptance=False,
            scope='real saved-input sleeve and character rebuild; existing material, isolated jobs; not PSD import or full motion replay')
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        characters.close(); sleeves.close()


if __name__ == '__main__':
    main()
