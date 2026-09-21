"""Own Windows worker descendants before any decoder or generator code runs."""
import os
import subprocess

from ..windows_process_job import attach_kill_on_close_process_job
from ..windows_suspended_process import resume_suspended_primary_thread
from .motion_intake_process import terminate_tree
from .pipeline_run import PipelineRunError


def launch(command, log):
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=os.name != 'nt',
                               creationflags=0x00000004 if os.name == 'nt' else 0)
    owner = None
    try:
        # The non-inheritable job handle belongs to the service. If the service
        # crashes, Windows closes it and kills workers, including grandchildren.
        owner = attach_kill_on_close_process_job(process)
        resume_suspended_primary_thread(process)
        return process, owner
    except Exception as exc:
        try:
            if owner is not None:
                owner.close()
        finally:
            if process.poll() is None:
                process.kill()  # Still suspended if ownership was not established.
            process.wait(timeout=10)
        raise PipelineRunError('motion_process_ownership_failed') from exc


def stop(process, owner):
    try:
        if owner is not None and owner.owns_windows_process_tree:
            owner.close()  # Also closes descendants after the worker has exited.
            process.wait(timeout=10)
        else:
            terminate_tree(process)
    except Exception as exc:
        raise PipelineRunError('motion_termination_failed') from exc
