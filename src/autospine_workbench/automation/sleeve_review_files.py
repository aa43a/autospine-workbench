"""Serve only byte-verified review artifacts from completed workflow stages."""
from hashlib import sha256
from pathlib import Path
import re

from .pipeline_run import PipelineRunError
from .storage_io import directory, read_document
from ..safe_input_files import read_real_file

STAGES = {'repair', 'cuff', 'boundary', 'framebuffer'}
TYPES = {'.html': 'text/html; charset=utf-8', '.json': 'application/json', '.png': 'image/png'}


def read(root, project, report, parts):
    if (len(parts) < 2 or parts[0] not in STAGES
            or any(not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.(?:html|json|png))?', p) for p in parts[1:])):
        raise PipelineRunError('pipeline_request_invalid')
    stage = parts[0]
    if not any(s['id'] == stage and s['status'] == 'succeeded' for s in report['steps']):
        raise PipelineRunError('pipeline_preview_not_ready')
    relative = Path(*parts[1:])
    # The framebuffer index is the only page at a stage root.
    if relative.as_posix() != 'index.html' or stage != 'framebuffer':
        if parts[1] != project:
            raise PipelineRunError('pipeline_request_invalid')
    mime = TYPES.get(relative.suffix)
    if mime is None:
        raise PipelineRunError('pipeline_request_invalid')
    base = directory(root / stage).resolve()
    path = base / relative
    if base not in path.resolve().parents:
        raise PipelineRunError('pipeline_request_invalid')
    expected = read_document(root / 'receipts' / (stage + '.json'))['files'].get(relative.as_posix())
    if not expected:
        raise PipelineRunError('pipeline_preview_not_ready')
    directory(path.parent)
    raw = read_real_file(path, 128 << 20, 'sleeve review')
    if sha256(raw).hexdigest() != expected:
        raise PipelineRunError('sleeve_cached_output_changed')
    return raw, mime
