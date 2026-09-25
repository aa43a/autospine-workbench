"""Mesh-bound garment intent; stored as a plan, never as solved constraints."""
from .pipeline_run import PipelineRunError
from .motion_partition_draft import meshes

KINDS = {'fixed', 'sliding', 'free'}


def validate(manager, job, body):
    part = body.get('contact_scope')
    if part is None:
        if body['action'] == 'contact_scope':
            raise PipelineRunError('motion_contact_scope_required')
        return None
    if (body['action'] != 'contact_scope' or not isinstance(part, dict)
            or set(part) != {'mesh_sha256', 'reference_slot', 'regions'}
            or not isinstance(part['regions'], dict) or set(part['regions']) != KINDS):
        raise PipelineRunError('motion_contact_scope_invalid')
    from .motion_target_jobs import context
    result, files = context(manager, job)
    report = meshes(files, result['artifact_sha256'])
    row = next((r for r in report['rows'] if r['slot'] == body['slot']), None)
    if (row is None or body['artifact_sha256'] != report['artifact_sha256']
            or part['mesh_sha256'] != row['mesh_sha256']):
        raise PipelineRunError('motion_contact_mesh_changed')
    reference = next((r for r in report['rows'] if r['slot'] == part['reference_slot']), None)
    if reference is None or reference['slot'] == row['slot']:
        raise PipelineRunError('motion_contact_reference_invalid')
    count = len(row['triangles'])//3
    seen = set(); regions = {}
    for kind in sorted(KINDS):
        ids = part['regions'][kind]
        if (not isinstance(ids, list) or len(ids)>10000
                or any(type(i) is not int or not 0<=i<count for i in ids)
                or len(set(ids)) != len(ids) or seen.intersection(ids)):
            raise PipelineRunError('motion_contact_regions_invalid')
        seen.update(ids); regions[kind] = sorted(ids)
    if not seen:
        raise PipelineRunError('motion_contact_regions_empty')
    return dict(mesh_sha256=part['mesh_sha256'], reference_slot=reference['slot'],
                reference_mesh_sha256=reference['mesh_sha256'], regions=regions,
                unclassified_triangles=count-len(seen), authority='none',
                status='proposed_contact_scope_not_solved')
