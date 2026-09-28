"""Read-only, exact-source timeline for an existing character candidate."""
import json
import math

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document


def link(manager, job, result):
    """Small, read-only source/clip binding; no bundle or framebuffer loading."""
    request = read_document(manager.folder(job) / 'request.json')
    source = manager.get(request['source_job_id'])
    if canonical_sha256(source) != request['source_job_sha256']:
        raise PipelineRunError('motion_target_source_changed')
    info = source['result']
    if (request.get('job_id') != job or request.get('kind') != 'adapt'
            or source.get('job_id') != request['source_job_id']
            or source.get('status') != 'succeeded'
            or source.get('kind', 'import') not in ('import', 'generate')
            or not request.get('motion_identity')
            or request['motion_identity'] != info.get('motion')):
        raise PipelineRunError('motion_target_source_identity_mismatch')
    clip = request.get('clip')
    if clip != result.get('clip'):
        raise PipelineRunError('motion_target_clip_changed')
    if request.get('layer_edits') != result.get('layer_edits'):
        raise PipelineRunError('motion_target_layer_edits_changed')
    fps = info['fps']; count = info['frame_count']; duration = info['duration_seconds']
    if (type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0
            or type(count) is not int or count < 2
            or type(duration) not in (int, float) or not math.isfinite(duration)
            or abs(duration - (count-1)/fps) > 1e-6):
        raise PipelineRunError('motion_source_time_invalid')
    start, end = 0, info['duration_seconds']
    if clip is not None:
        from ..targets.character43.motion_clip import validate
        validate(clip, info['frame_count'])
        start, end = clip['start_frame'] / fps, clip['end_frame'] / fps
    return dict(artifact_sha256=result['artifact_sha256'], source_job_id=source['job_id'],
                source_sha256=source['source_sha256'], source_start=start, source_end=end,
                duration=end-start, target_job_id=job, motion_identity=request['motion_identity'],
                source_fps=fps, source_frame_count=count, source_duration=duration,
                clip=clip, layer_edits=request.get('layer_edits'), authority='none',
                scope='nearest_source_samples_with_exact_clip_time_offset')


def build(manager, job, result):
    report = link(manager, job, result)
    return dict(report, preview=json.loads(manager.preview(report['source_job_id'])))
