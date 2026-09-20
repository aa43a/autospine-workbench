"""Reproject exact source bytes, retaining recorded generation and parent identity."""
from hashlib import sha256
from io import BytesIO

from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .pipeline_run import PipelineRunError
from .storage_io import read_document


def submit(manager, job_id, body):
    automatic = set(body) == {'view', 'comparison_sha256'}
    if (set(body) != {'view'} and not automatic) or body.get('view') not in ('front', 'side'):
        raise PipelineRunError('motion_view_invalid')
    source = manager.get(job_id)
    if source['status'] != 'succeeded' or source.get('kind') == 'adapt':
        raise PipelineRunError('motion_target_source_unavailable')
    folder = manager.folder(job_id)
    raw = read_real_file(folder / ('source.'+source['format']), 64 << 20, 'motion source')
    if sha256(raw).hexdigest() != source['source_sha256']:
        raise PipelineRunError('motion_source_changed')
    request = read_document(folder / 'request.json')
    recorded = None
    if source['format'] == 'npz' and source['result'].get('motion_status') == 'compiled':
        motion = source['result']['motion']
        bundle = VerifiedMotionBundleReader(manager.state_root).load(motion['clip_sha256'], motion['bundle_sha256'])
        if bundle.raw_npz != raw:
            raise PipelineRunError('motion_source_changed')
        if bundle.kimodo_source['producer']['status'] == 'recorded':
            recorded = bundle.kimodo_source['producer']
    derivation = dict(kind='view_selection', parent_job_id=job_id,
                      source_name=source.get('derivation', {}).get('source_name', source['name']),
                      parent_job_sha256=canonical_sha256(source), source_sha256=source['source_sha256'])
    if automatic:
        from .motion_view_comparison import inspect
        comparison = inspect(manager, job_id)
        if (comparison['comparison_sha256'] != body['comparison_sha256'] or
                comparison['recommended_view'] != body['view']):
            raise PipelineRunError('motion_view_comparison_changed')
        derivation.update(selection_profile=comparison['profile'], comparison_sha256=body['comparison_sha256'])
    # Generated prompts are display labels, not file names.
    return manager.upload(BytesIO(raw), len(raw), 'view-'+job_id[-8:]+'.'+source['format'],
                          body['view'], request.get('npz_options'), derivation=derivation, producer=recorded)
