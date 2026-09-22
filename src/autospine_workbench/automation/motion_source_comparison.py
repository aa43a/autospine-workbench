"""Read-only, exact-source timeline for an existing character candidate."""
import json
import math

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document


def build(manager, job, result):
    request = read_document(manager.folder(job) / 'request.json')
    source = manager.get(request['source_job_id'])
    if canonical_sha256(source) != request['source_job_sha256']:
        raise PipelineRunError('motion_target_source_changed')
    preview = json.loads(manager.preview(source['job_id']))
    info = source['result']
    clip = request.get('clip')
    if clip != result.get('clip'):
        raise PipelineRunError('motion_target_clip_changed')
    fps = info['fps']
    if not math.isfinite(fps) or fps <= 0:
        raise PipelineRunError('motion_source_time_invalid')
    start, end = 0, info['duration_seconds']
    if clip is not None:
        from ..targets.character43.motion_clip import validate
        validate(clip, info['frame_count'])
        start, end = clip['start_frame'] / fps, clip['end_frame'] / fps
    return dict(artifact_sha256=result['artifact_sha256'], source_job_id=source['job_id'],
                source_sha256=source['source_sha256'], source_start=start, source_end=end,
                duration=end-start, preview=preview, authority='none',
                scope='nearest_source_samples_with_exact_clip_time_offset')
