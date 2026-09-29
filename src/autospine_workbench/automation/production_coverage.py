"""Expose unresolved character regions without equating a built job with coverage."""
from urllib.parse import quote

from .pipeline_run import PipelineRunError


def summarize(job):
    rows = []
    for layer in job.get('layers', []):
        regions = layer.get('regions', [])
        unresolved = (layer.get('state') in ('static_reference', 'missing', 'partial')
                      or bool(layer.get('missing_region_ids'))
                      or any(r.get('state') in ('static_reference', 'missing') for r in regions))
        rows.append(dict(layer_id=layer['layer_id'], name=layer.get('name', layer['layer_id']),
                         state=layer.get('state', 'unknown'), unresolved=unresolved,
                         reason_codes=layer.get('reason_codes', []), regions=regions,
                         missing_region_ids=layer.get('missing_region_ids', [])))
    return dict(layers=rows, layer_count=len(rows), unresolved_layer_count=sum(r['unresolved'] for r in rows),
                scope='character_layer_coverage_not_motion_or_visual_acceptance', authority='none')


def inspect(manager, run_id):
    run = manager.get(run_id)
    stage = run['stages']['character']
    if stage['status'] != 'succeeded' or not stage.get('job_id'):
        raise PipelineRunError('production_character_not_ready')
    character = manager.driver.motions.character_manager()
    project = run['request']['project_id']
    job, _ = character.verified_snapshot(project, stage['job_id'])
    if job['artifact_sha256'] != stage['artifact_sha256']:
        raise PipelineRunError('production_completed_child_changed')
    result = summarize(job)
    prefix = f"/api/projects/{quote(project, safe='')}/automation/character/jobs/{stage['job_id']}/view/"
    result.update(project_id=project, character_job_id=stage['job_id'], artifact_sha256=job['artifact_sha256'],
                  review_url=prefix + 'index.html', static_regions_url=prefix + 'static-regions/index.html',
                  edit_url=f"/?project={quote(project, safe='')}")
    return result
