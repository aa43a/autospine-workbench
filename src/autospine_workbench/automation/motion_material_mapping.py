"""Versioned same-canvas material regions and intervals; no implicit application."""
from io import BytesIO
import json
import math
from zipfile import ZipFile
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


def history(manager, job):
    root = manager.folder(job)/'material-mappings'
    if not root.exists():return []
    directory(root);rows=[];previous=None
    paths=sorted(root.glob('mapping-*.json'))
    if len(paths)>1000:raise PipelineRunError('motion_material_mapping_limit')
    for i,path in enumerate(paths,1):
        row=read_document(path)
        if (path.name!=f'mapping-{i:04d}.json' or row['revision']!=i or row['job_id']!=job
                or row['previous_sha256']!=previous):
            raise PipelineRunError('motion_material_mapping_history_invalid')
        rows.append(row);previous=canonical_sha256(row)
    return rows


def inspect(manager, job):
    with manager._lock:
        rows=history(manager,job)
        return dict(job_id=job,revision=len(rows),history=rows,authority='none',replacement_applied=False)


def validate(files, receipt, body):
    from .motion_partition_draft import meshes
    from ..targets.character43.numeric_reference import read
    rows=meshes(files,receipt['artifact_sha256'])['rows']
    row=next((r for r in rows if r['slot']==receipt['slot']),None)
    if row is None or row['mesh_sha256']!=body['mesh_sha256']:
        raise PipelineRunError('motion_material_mapping_mesh_changed')
    selected=body['triangles'];times=body['interval']
    if (not isinstance(selected,list) or not 1<=len(selected)<=10000
            or any(type(i) is not int or not 0<=i<len(row['triangles'])//3 for i in selected)
            or len(set(selected))!=len(selected)):
        raise PipelineRunError('motion_material_mapping_region_invalid')
    frames=read(files)['animations'][receipt['animation']]
    if (not isinstance(times,list) or len(times)!=2
            or any(type(t) not in (int,float) or not math.isfinite(t) for t in times)
            or not 0<=times[0]<times[1]<=max(f['time'] for f in frames)):
        raise PipelineRunError('motion_material_mapping_interval_invalid')
    return dict(mesh_sha256=row['mesh_sha256'],triangles=sorted(selected),interval=times,
        uv_policy='same_canvas_original_uv',geometry_policy='preserve_original_weights_and_deform',
        activation_policy='start_inclusive_end_exclusive_not_blend_or_visual_acceptance')


def save(manager, job, body):
    from .motion_material_return import inspect as returns
    from .motion_repair_material import download
    from .motion_target_jobs import context
    fields={'expected_revision','action','material_bundle_sha256'}
    if not isinstance(body,dict) or body.get('action') not in ('map','withdraw'):
        raise PipelineRunError('motion_material_mapping_request_invalid')
    if body['action']=='map':fields|={'mesh_sha256','triangles','interval'}
    if set(body)!=fields or type(body['expected_revision']) is not int:
        raise PipelineRunError('motion_material_mapping_request_invalid')
    with manager._lock:
        rows=history(manager,job)
        if body['expected_revision']!=len(rows):raise PipelineRunError('motion_material_mapping_revision_changed')
        if len(rows)>=1000:raise PipelineRunError('motion_material_mapping_limit')
        found=[r for r in returns(manager,job)['returns'] if r['material_bundle_sha256']==body['material_bundle_sha256']]
        if len(found)!=1:raise PipelineRunError('motion_material_mapping_return_missing')
        receipt=found[0];mapping=None
        if body['action']=='map':
            with ZipFile(BytesIO(download(manager,job,str(receipt['draft_revision'])))) as archive:
                request=json.loads(archive.read('request.json'))
            from .animated_store import AnimatedStore
            stored=AnimatedStore(manager.folder(job)/'material-returns').read(receipt['material_bundle_sha256'])
            original_request=json.loads(stored['request.json'])
            if (canonical_sha256(original_request)!=receipt['request_sha256'] or original_request!=request):
                raise PipelineRunError('motion_material_mapping_request_changed')
            result,files=context(manager,job)
            if result['artifact_sha256']!=receipt['artifact_sha256']:
                raise PipelineRunError('motion_material_mapping_candidate_changed')
            mapping=validate(files,receipt,body)
        elif not any(r['material_bundle_sha256']==body['material_bundle_sha256'] for r in rows):
            raise PipelineRunError('motion_material_mapping_missing')
        row=dict(schema='autospine.motion-material-mapping/v1',job_id=job,revision=len(rows)+1,
            previous_sha256=canonical_sha256(rows[-1]) if rows else None,action=body['action'],
            material_bundle_sha256=receipt['material_bundle_sha256'],draft_sha256=receipt['draft_sha256'],
            artifact_sha256=receipt['artifact_sha256'],slot=receipt['slot'],animation=receipt['animation'],
            mapping=mapping,authority='none',replacement_applied=False)
        root=directory(manager.folder(job)/'material-mappings',create=True)
        if not publish_document(root/f"mapping-{row['revision']:04d}.json",row,staging=root/'staging'):
            raise PipelineRunError('motion_material_mapping_revision_changed')
        return dict(job_id=job,revision=len(rows)+1,history=rows+[row],authority='none',replacement_applied=False)
