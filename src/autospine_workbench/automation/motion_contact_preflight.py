"""Read-only preflight of one current immutable contact-scope draft."""
import json
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError


def read(manager, job, parts, result, files):
    from .motion_repair_draft import evidence, history
    from ..targets.character43.active_mesh_pose import sample_active
    from ..targets.character43.contact_scope_constraints import inspect
    from ..targets.character43.occlusion_scope_order import inspect as inspect_order, timeline
    if len(parts)!=2 or not parts[1].endswith('.json') or not parts[1][:-5].isdigit():
        raise PipelineRunError('pipeline_artifact_not_found')
    revision=int(parts[1][:-5])
    if not 1<=revision<=1000:raise PipelineRunError('pipeline_artifact_not_found')
    with manager._lock: rows=history(manager,job)
    if revision>len(rows):raise PipelineRunError('motion_contact_plan_unavailable')
    row=rows[revision-1]
    key=lambda r:(r['slot'],r['animation'],r['event']['triangle'],r['event']['time'])
    if row['action']!='contact_scope' or any(key(r)==key(row) for r in rows[revision:]):
        raise PipelineRunError('motion_contact_plan_changed')
    report, digest=evidence(manager,job)
    if (row['artifact_sha256']!=result['artifact_sha256'] or report['artifact_sha256']!=result['artifact_sha256']
            or row['evidence_sha256']!=digest):
        raise PipelineRunError('motion_contact_plan_changed')
    doc=json.loads(files['skeleton.json']); scope=row['contact_scope']
    slot, reference=row['slot'],scope['reference_slot']
    choices=doc['skins'][0]['attachments']
    if (canonical_sha256(choices[slot][slot])!=scope['mesh_sha256'] or
            canonical_sha256(choices[reference][reference])!=scope['reference_mesh_sha256']):
        raise PipelineRunError('motion_contact_mesh_changed')
    pose=sample_active(doc,row['animation'],row['event']['time'])
    if pose['attachments'].get(slot)!=slot or pose['attachments'].get(reference)!=reference:
        raise PipelineRunError('motion_contact_active_attachment_unsupported')
    output=inspect(pose['setup_vertices'][slot],pose['vertices'][slot],pose['triangles'][slot],
                   pose['setup_vertices'][reference],pose['vertices'][reference],pose['triangles'][reference],scope['regions'])
    if output['occlusion_review']['required']:
        from .motion_occlusion_alpha import read as read_alpha
        order=inspect_order(doc,row['animation'],row['event']['time'],slot,reference)
        output['occlusion_review']['draw_order']=order
        output['occlusion_review']['order_timeline']=timeline(doc,row['animation'],slot,reference)
        from ..targets.character43.occlusion_scope_partition import build as partition_scope
        try:
            _,partition=partition_scope(doc,slot,scope)
            output['occlusion_review']['render_partition']=dict(status='prepared',**partition)
        except ValueError as error:
            output['occlusion_review']['render_partition']=dict(status='unavailable',reason_code=str(error))
        output['occlusion_review']['texture_samples']=read_alpha(doc,files,pose,slot,reference,
                                                               scope['regions']['occlusion'],row['animation'])
        if not order['reference_can_cover_in_order']:
            output['reasons'].append('occlusion_reference_behind')
            output['status']='requires_changes'
    output.update(artifact_sha256=result['artifact_sha256'],draft_sha256=canonical_sha256(row),revision=revision,
                  slot=slot,reference_slot=reference,animation=row['animation'],time=row['event']['time'])
    with manager._lock:
        if canonical_sha256(history(manager,job))!=canonical_sha256(rows):
            raise PipelineRunError('motion_contact_plan_changed')
    return json.dumps(output,ensure_ascii=False,allow_nan=False).encode(), 'application/json'
