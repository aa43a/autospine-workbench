"""Exact mesh-bound region selection, stored within the existing repair history."""
import json
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError


def meshes(files,artifact):
    from ..targets.character43.region_order_interval import duration
    doc=json.loads(files['skeleton.json']);rows=[]
    for slot,choices in doc['skins'][0]['attachments'].items():
        mesh=choices[slot]
        if mesh.get('type')!='mesh':continue
        rows.append(dict(slot=slot,mesh_sha256=canonical_sha256(mesh),
            uvs=mesh['uvs'],triangles=mesh['triangles'],texture_path='images/'+mesh.get('path',slot)+'.png'))
    return dict(artifact_sha256=artifact,rows=rows,bones=[b['name'] for b in doc['bones']],
        animations=[dict(name=name,duration=duration(value)) for name,value in doc.get('animations',{}).items()],
        slots=[s['name'] for s in doc['slots']],
        authority='none',selected=False)


def validate(manager,job,body):
    if 'partition' not in body:return None
    from .motion_target_jobs import context
    result,files=context(manager,job);report=meshes(files,result['artifact_sha256'])
    part=body['partition']
    if body['action']!='partition' or not isinstance(part,dict) or set(part)!={'mesh_sha256','triangles','bone'}:
        raise PipelineRunError('motion_partition_request_invalid')
    rows=[r for r in report['rows'] if r['slot']==body['slot']]
    if (len(rows)!=1 or body['artifact_sha256']!=report['artifact_sha256']
            or part['mesh_sha256']!=rows[0]['mesh_sha256']):
        raise PipelineRunError('motion_partition_mesh_changed')
    triangles=part['triangles'];count=len(rows[0]['triangles'])//3
    if (not isinstance(triangles,list) or not 1<=len(triangles)<=10000
            or any(type(i) is not int or not 0<=i<count for i in triangles)
            or len(set(triangles))!=len(triangles) or part['bone'] not in report['bones']):
        raise PipelineRunError('motion_partition_selection_invalid')
    return dict(mesh_sha256=part['mesh_sha256'],triangles=sorted(triangles),bone=part['bone'],
        status='proposed_region_not_applied',authority='none')


def validate_order(manager, job, body):
    if 'region_order' not in body:
        if body['action'] == 'region_order':
            raise PipelineRunError('motion_region_order_required')
        return None
    part = body['region_order']
    if (body['action'] != 'region_order' or not isinstance(part, dict)
            or set(part) not in ({'mesh_sha256', 'triangles', 'reference_slot', 'side'},
                                {'mesh_sha256', 'triangles', 'reference_slot', 'side', 'interval'})):
        raise PipelineRunError('motion_region_order_invalid')
    from .motion_target_jobs import context
    from ..targets.character43.region_order_candidate import build
    result, files = context(manager, job)
    document = json.loads(files['skeleton.json'])
    report = meshes(files, result['artifact_sha256'])
    row = next((r for r in report['rows'] if r['slot'] == body['slot']), None)
    if (row is None or body['artifact_sha256'] != report['artifact_sha256']
            or part['mesh_sha256'] != row['mesh_sha256']):
        raise PipelineRunError('motion_partition_mesh_changed')
    try:
        options = dict(animation=body['animation'], interval=part['interval']) if 'interval' in part else {}
        if 'interval' in part and part['interval'] is None:
            raise ValueError('region_order_interval_invalid')
        build(document, body['slot'], part['triangles'], part['reference_slot'], part['side'], **options)
    except (ValueError, TypeError, KeyError) as error:
        raise PipelineRunError('motion_region_order_unsupported') from error
    return dict(part, triangles=sorted(part['triangles']), authority='none',
                status='proposed_interval_order_not_applied' if 'interval' in part else 'proposed_static_order_not_applied')
