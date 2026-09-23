"""Exact mesh-bound region selection, stored within the existing repair history."""
import json
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError


def meshes(files,artifact):
    doc=json.loads(files['skeleton.json']);rows=[]
    for slot,choices in doc['skins'][0]['attachments'].items():
        mesh=choices[slot]
        if mesh.get('type')!='mesh':continue
        rows.append(dict(slot=slot,mesh_sha256=canonical_sha256(mesh),
            uvs=mesh['uvs'],triangles=mesh['triangles'],texture_path='images/'+mesh.get('path',slot)+'.png'))
    return dict(artifact_sha256=artifact,rows=rows,bones=[b['name'] for b in doc['bones']],
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
