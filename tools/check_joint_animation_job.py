"""Build an exact M5 candidate through the same queue used by the workbench."""
import argparse
import json
from pathlib import Path
import time

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_joint_jobs import inspect, submit


def sample_config(meta, loop):
    config = meta['defaults']
    config['loop'] = loop
    config['face']['enabled'] = config['hair']['enabled'] = config['cloth']['enabled'] = True
    config['face']['mouth']['template_enabled'] = True
    duration = meta['duration']
    for channel, values in (
        ('mouth', [('open', .65), ('wide', .15)]),
        ('gaze', [('x', .4), ('y', .1)]),
        ('brows', [('lift', .25), ('tilt', .1)]),
        ('turn', [('yaw', .1), ('pitch', .05)]),
    ):
        config['face'][channel]['keys'] = [
            dict(time=duration*f, **{key: value*gain for key, value in values})
            for f, gain in ((0,0), (.2,0), (.35,1), (.5,0), (.8,0), (1,0))]
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('body')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    parser.add_argument('--registration')
    options = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    projects = ProjectStore(repo.parent, repo/'workspace')
    sleeves = SleeveWebJobs(projects)
    characters = CharacterJobs(projects, sleeves)
    manager = MotionIntakeJobs(projects)
    manager.character_manager = lambda: characters
    try:
        meta = inspect(manager, options.body, options.registration)
        config = sample_config(meta, options.loop)
        options.output.parent.mkdir(parents=True, exist_ok=True)
        if options.inspect_only:
            options.output.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
            print(json.dumps(dict(status='inspected', duration=meta['duration'], eligibility=meta['eligibility'])), flush=True)
            return
        body = dict(artifact_sha256=meta['artifact_sha256'], config=config)
        if options.registration: body['registration_sha256'] = options.registration
        value = submit(manager, options.body, body)
        job = value['job_id']
        options.output.write_text(json.dumps(dict(parent=options.body, job_id=job, config=config)), encoding='utf-8')
        print(json.dumps(dict(job_id=job, status='submitted')), flush=True)
        previous = None
        while value['status'] in ('pending', 'running'):
            time.sleep(2)
            value = manager.get(job)
            stage = (value['status'], value.get('step'))
            if stage != previous:
                print(json.dumps(dict(job_id=job, status=stage[0], step=stage[1])), flush=True)
                previous = stage
        options.output.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        result = value.get('result', {})
        print(json.dumps(dict(job_id=job, status=value['status'], artifact=result.get('artifact_sha256'),
                             frames=result.get('runtime', {}).get('frames'), geometry=result.get('geometry_passed'),
                             reason=value.get('reason_code')), ensure_ascii=False), flush=True)
        if value['status'] != 'succeeded':
            raise RuntimeError('joint_e2e_failed')
    finally:
        manager.close(); characters.close(); sleeves.close()


if __name__ == '__main__':
    main()
