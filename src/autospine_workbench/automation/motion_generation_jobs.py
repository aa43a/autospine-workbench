"""Bounded text requests, with server-owned runtime and immutable generation jobs."""
from copy import deepcopy
import math
import os
from pathlib import Path
from threading import Event
from uuid import uuid4

from .pipeline_run import PipelineRunError
from .storage_io import publish_document

MODEL = 'Kimodo-SOMA-RP-v1.1'


def runtime_root(manager):
    workspace = getattr(manager.projects, 'workspace_root', manager.state_root.parent)
    return Path(os.environ.get('AUTOSPINE_KIMODO_RUNTIME', str(Path(workspace) / 'kimodo-runtime'))).resolve()


def availability(manager):
    root = runtime_root(manager)
    return 'configured' if all((root / p).is_file() for p in (
        'tools/modelscope_text_encoder.py', '.venv/Scripts/python.exe',
        'checkpoints/' + MODEL + '/model.safetensors')) else 'unavailable'


def options(body):
    fields = {'prompt', 'duration_seconds', 'seed', 'diffusion_steps', 'view'}
    if not isinstance(body, dict) or set(body) != fields:
        raise PipelineRunError('motion_generation_request_invalid')
    prompt = body['prompt']
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1000 or any(ord(c) < 32 for c in prompt):
        raise PipelineRunError('motion_generation_prompt_invalid')
    if len([part for part in prompt.split('.') if part.strip()]) != 1:
        raise PipelineRunError('motion_generation_single_prompt_required')
    duration = body['duration_seconds']
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 1 <= duration <= 10:
        raise PipelineRunError('motion_generation_duration_invalid')
    if type(body['seed']) is not int or not 0 <= body['seed'] <= 2**31-1:
        raise PipelineRunError('motion_generation_seed_invalid')
    if type(body['diffusion_steps']) is not int or not 10 <= body['diffusion_steps'] <= 100:
        raise PipelineRunError('motion_generation_steps_invalid')
    if body['view'] not in ('front', 'side'):
        raise PipelineRunError('motion_view_invalid')
    return dict(body, prompt=prompt.strip())


def submit(manager, body):
    selected = options(body)
    if availability(manager) != 'configured':
        raise PipelineRunError('motion_generation_unavailable')
    with manager._lock:
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-' + uuid4().hex
        folder = manager.folder(job, True)
        value = dict(job_id=job, kind='generate', name=selected['prompt'][:80], format='npz',
                     view=selected['view'], status='pending', step='queued', authority='none')
        request = dict(value, generation=selected, model=MODEL,
                       npz_options=dict(profile='kimodo-soma77-v1', fps='30'))
        publish_document(folder / 'request.json', request, staging=folder / 'staging')
        manager._jobs[job] = value
        manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)
