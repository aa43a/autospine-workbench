"""Disposable manager host for abrupt-exit tests; never runs a real model."""
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

from autospine_workbench.automation.motion_generation_jobs import submit
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs


def main(root):
    manager = MotionIntakeJobs(SimpleNamespace(state_root=root / 'state', workspace_root=root))
    original = subprocess.Popen

    def launch(command, **kwargs):
        worker = (
            'import os,subprocess,sys,time,json; from pathlib import Path; '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
            'Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid])); time.sleep(60)'
        )
        return original([sys.executable, '-c', worker, str(root / 'pids.json')], **kwargs)

    with patch('autospine_workbench.automation.motion_generation_jobs.availability',
               return_value='configured'), patch(
                   'autospine_workbench.automation.motion_process_owner.subprocess.Popen',
                   side_effect=launch):
        job = submit(manager, dict(prompt='A person waves.', duration_seconds=4,
                                  seed=42, diffusion_steps=100, view='front'))
        (root / 'job.json').write_text(json.dumps(job))
        time.sleep(60)
        manager.close()


if __name__ == '__main__':
    main(Path(sys.argv[1]))
