"""Permit an explicit order edit after a verified scope representation only."""
from hashlib import sha256
import json
from .pipeline_run import PipelineRunError
from ..resolved_project import canonical_sha256
from ..targets.character43.occlusion_scope_bundle import PROFILE


def verify(manager,parent_job,request,row,artifact):
    parent=request.get('repair_execution')
    if not parent:return None
    if parent.get('profile')!=PROFILE or row['action']!='region_order':
        raise PipelineRunError('motion_repair_nested_execution_unsupported')
    from .motion_target_jobs import context
    result,files=context(manager,parent_job)
    raw=files.get('motion-repair-provenance.json')
    if result['artifact_sha256']!=artifact or raw is None:
        raise PipelineRunError('motion_scope_parent_changed')
    provenance=json.loads(raw)
    if (any(provenance.get(k)!=v for k,v in parent.items())
            or provenance.get('profile')!=PROFILE
            or canonical_sha256(provenance['draft'])!=provenance['draft_sha256']):
        raise PipelineRunError('motion_scope_parent_changed')
    # New draft binds to the new mesh, not the parent's triangle inventory.
    document=json.loads(files['skeleton.json'])
    mesh=document['skins'][0]['attachments'].get(row['slot'],{}).get(row['slot'])
    if mesh is None or canonical_sha256(mesh)!=row['region_order']['mesh_sha256']:
        raise PipelineRunError('motion_scope_parent_mesh_changed')
    expected=sha256(raw).hexdigest()
    from .motion_repair_lineage import carry
    carry(files,dict(parent_job_id=parent_job,parent_artifact_sha256=artifact,parent_repair_sha256=expected))
    return expected
