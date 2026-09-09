"""Explicit isolated DWPose process; the service never imports inference dependencies."""

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import time
from uuid import uuid4

from ..manifest_artifacts import require_safe_token, require_sha256
from ..pose_observations import load_pose_observations
from ..resolved_project import canonical_sha256
from ..runners.pose.dwpose_profile import MODEL_BYTES, MODEL_SHA256
from ..safe_input_files import read_real_file, strict_json_object
from .animated_store import _publish_bytes
from .storage_io import directory, publish_document

MAX_LOG = 1 << 20


class PosePreparationError(ValueError):
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class PoseRunnerConfig:
    python: Path | None = None
    model: Path | None = None
    timeout_seconds: float = 120

    @classmethod
    def from_environment(cls, environment=None):
        env = os.environ if environment is None else environment
        return cls(Path(env['AUTOSPINE_POSE_PYTHON']) if env.get('AUTOSPINE_POSE_PYTHON') else None,
                   Path(env['AUTOSPINE_POSE_MODEL']) if env.get('AUTOSPINE_POSE_MODEL') else None)

    def public_status(self):
        """No local paths or exception strings enter normal user responses."""
        try:
            self.validate()
            fingerprint = tuple((p.stat().st_size, p.stat().st_mtime_ns) for p in (self.python, self.model))
            _probe(str(self.python.resolve()), str(self.model.resolve()), fingerprint)
            return {'status': 'ready', 'reason_code': None, 'authority': 'none',
                    'runner': 'dwpose-wholebody-fullcanvas-v1', 'model_sha256': MODEL_SHA256}
        except (PosePreparationError, OSError, ValueError) as exc:
            return {'status': 'missing', 'reason_code': getattr(exc, 'reason_code', 'pose_runner_unavailable'),
                    'authority': 'none'}

    def validate(self):
        if not isinstance(self.python, Path) or not isinstance(self.model, Path):
            raise PosePreparationError('pose_runner_not_configured')
        if type(self.timeout_seconds) not in (int, float) or not .05 <= self.timeout_seconds <= 600:
            raise PosePreparationError('pose_runner_configuration_invalid')
        if not self.python.is_absolute() or not self.model.is_absolute():
            raise PosePreparationError('pose_runner_configuration_invalid')
        if not self.python.is_file() or not self.model.is_file():
            raise PosePreparationError('pose_runner_unavailable')


@lru_cache(maxsize=8)
def _probe(python, model, fingerprint):
    raw = read_real_file(Path(model), MODEL_BYTES, 'Pinned pose model')
    if len(raw) != MODEL_BYTES or hashlib.sha256(raw).hexdigest() != MODEL_SHA256:
        raise PosePreparationError('pose_runner_model_mismatch')
    script = ('import importlib.util,sys; '
              'sys.exit(0 if all(importlib.util.find_spec(x) is not None '
              'for x in ("onnxruntime","numpy","cv2")) else 2)')
    try:
        result = subprocess.run([python, '-I', '-c', script], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=10, check=False, creationflags=_creationflags())
    except (OSError, subprocess.SubprocessError) as exc:
        raise PosePreparationError('pose_runner_unavailable') from exc
    if result.returncode:
        raise PosePreparationError('pose_runner_dependencies_missing')


def _creationflags():
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _run_child(arguments, folder, timeout_seconds, cancel_requested, environment):
    """Bound stdout/stderr and stop the owned single inference process on cancellation."""
    if cancel_requested():
        raise PosePreparationError('pipeline_canceled')
    logs = [folder / 'stdout.log', folder / 'stderr.log']
    child = None
    try:
        with logs[0].open('xb') as stdout, logs[1].open('xb') as stderr:
            child = subprocess.Popen(arguments, cwd=str(Path(__file__).resolve().parents[3]),
                                     env=environment, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                     shell=False, creationflags=_creationflags())
            start = time.monotonic()
            while child.poll() is None:
                if cancel_requested():
                    raise PosePreparationError('pipeline_canceled')
                if time.monotonic() - start >= timeout_seconds:
                    raise PosePreparationError('pose_runner_timeout')
                if any(p.stat().st_size > MAX_LOG for p in logs):
                    raise PosePreparationError('pose_runner_output_limit')
                time.sleep(.05)
            if any(p.stat().st_size > MAX_LOG for p in logs):
                raise PosePreparationError('pose_runner_output_limit')
            if cancel_requested():
                raise PosePreparationError('pipeline_canceled')
            if child.returncode != 0:
                raise PosePreparationError('pose_runner_failed')
    except OSError as exc:
        raise PosePreparationError('pose_runner_unavailable') from exc
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    return read_real_file(logs[0], MAX_LOG, 'Pose runner status')


def run_project_pose(config, project_id, composite, expected_sha256, state_root,
                     cancel_requested=lambda: False):
    """Return validated canonical observations; raw tensors remain in the existing store."""
    try:
        require_safe_token(project_id, 'Pose project')
        require_sha256(expected_sha256, 'Pose source')
        if type(composite) is not bytes or not 24 <= len(composite) <= 64 << 20 \
                or hashlib.sha256(composite).hexdigest() != expected_sha256:
            raise PosePreparationError('pose_runner_source_mismatch')
        if composite[:8] != b'\x89PNG\r\n\x1a\n' or composite[12:16] != b'IHDR':
            raise PosePreparationError('pose_runner_source_invalid')
        canvas = struct.unpack('>II', composite[16:24])
        if any(not 0 < value <= 4096 for value in canvas):
            raise PosePreparationError('pose_runner_canvas_unsupported')
        if cancel_requested():
            raise PosePreparationError('pipeline_canceled')
        status = config.public_status()
        if status['status'] != 'ready':
            raise PosePreparationError(status['reason_code'])
        root = directory(Path(state_root).absolute(), create=True)
        folder = directory(root / 'jobs' / 'input-preparation-pose' / ('attempt-' + uuid4().hex), create=True)
        source, output = folder / 'source.png', folder / 'pose.json'
        _publish_bytes(source, composite)
        request = {'project_id': project_id, 'image_sha256': expected_sha256,
                   'canvas_size': list(canvas), 'model_sha256': MODEL_SHA256,
                   'runner': 'dwpose-wholebody-fullcanvas-v1', 'authority': 'none'}
        publish_document(folder / 'request.json', request, staging=folder / 'staging')
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]), PYTHONNOUSERSITE='1')
        arguments = [str(config.python), '-m', 'autospine_workbench.runners.pose',
                     '--image', str(source), '--project', project_id, '--model', str(config.model),
                     '--state-root', str(root), '--output', str(output)]
        raw_status = _run_child(arguments, folder, config.timeout_seconds, cancel_requested, env)
        reported = strict_json_object(raw_status, 'Pose runner status')
        document = strict_json_object(read_real_file(output, 1_000_000, 'Pose result'), 'Pose result')
        if reported.get('status') != 'succeeded' or reported.get('authority') != 'none' \
                or reported.get('pose_sha256') != canonical_sha256(document):
            raise PosePreparationError('pose_runner_result_invalid')
        pose = load_pose_observations(output, expected_project_id=project_id,
                                     expected_image_sha256=expected_sha256, expected_canvas_size=canvas)
        if read_real_file(source, 64 << 20, 'Pose source') != composite:
            raise PosePreparationError('pose_runner_source_mismatch')
        if cancel_requested():
            raise PosePreparationError('pipeline_canceled')
        return deepcopy(dict(pose.document))
    except PosePreparationError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise PosePreparationError('pose_runner_result_invalid') from exc
