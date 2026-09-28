"""Freeze a live additional-view handoff into the cancellable motion queue."""
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from threading import Event
from uuid import uuid4
from zipfile import ZipFile

from ..resolved_project import canonical_sha256
from ..targets.character43.view_pose_candidate import PROFILE
from ..targets.character43.view_pose_variant import source_mesh
from .motion_material_return import validate_png
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes, publish_document, read_document


def submit(manager, parent_job, body):
    from .motion_joint_jobs import require_body_repair_parent
    require_body_repair_parent(manager, parent_job)
    from .motion_repair_material import download
    from .motion_target_jobs import assert_current, context
    from .motion_repair_lineage import carry
    if not isinstance(body, dict) or set(body) != {'request', 'view_pose', 'png_base64'}:
        raise PipelineRunError('motion_view_request_invalid')
    handoff, pose = body['request'], deepcopy(body['view_pose'])
    if (not isinstance(handoff, dict) or type(handoff.get('draft_revision')) is not int
            or handoff.get('job_id') != parent_job or not isinstance(pose, dict)):
        raise PipelineRunError('motion_view_identity_invalid')
    png = validate_png(body['png_base64'], pose.get('texture_size'))
    if sha256(png).hexdigest() != pose.get('texture_sha256'):
        raise PipelineRunError('motion_view_texture_changed')
    with manager._lock:
        with ZipFile(BytesIO(download(manager, parent_job, str(handoff['draft_revision']), include_preview=False))) as archive:
            expected = json.loads(archive.read('request.json'))
        if expected != handoff or not expected.get('view_needs'):
            raise PipelineRunError('motion_view_handoff_changed')
        result, files = context(manager, parent_job)
        document = json.loads(files['skeleton.json'])
        if (result['artifact_sha256'] != expected['artifact_sha256'] or
                pose.get('document_sha256') != canonical_sha256(document) or
                pose.get('slot') != expected['slot'] or pose.get('animation') != expected['animation']):
            raise PipelineRunError('motion_view_candidate_changed')
        source_mesh(document, pose['slot'], pose['animation'])
        request = read_document(manager.folder(parent_job)/'request.json')
        assert_current(manager, request)
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        material = {'request.json': canonical_bytes(expected), 'view-pose.json': canonical_bytes(pose), 'view.png': png}
        digest = canonical_sha256({n: sha256(v).hexdigest() for n, v in material.items()})
        plan = dict(action='additional_view', artifact_sha256=result['artifact_sha256'],
                    slot=pose['slot'], animation=pose['animation'], material_bundle_sha256=digest)
        repair = dict(profile=PROFILE, parent_job_id=parent_job, parent_artifact_sha256=result['artifact_sha256'],
                      draft=plan, draft_sha256=canonical_sha256(plan))
        if 'motion-repair-provenance.json' in files:
            repair['parent_repair_sha256'] = sha256(files['motion-repair-provenance.json']).hexdigest()
        carry(files, repair)
        store = manager.character_manager().application.store
        if store.publish(material) != digest:
            raise PipelineRunError('motion_view_bundle_changed')
        job = 'motion-'+uuid4().hex
        root = manager.folder(job, True)
        request = deepcopy(request); request.update(job_id=job, repair_execution=repair)
        publish_document(root/'request.json', request, staging=root/'staging')
        value = dict(job_id=job, kind='adapt', project_id=request['project_id'],
                     character_job_id=request['character_job_id'], name=request['name']+' · 新视角候选',
                     status='pending', step='queued', authority='none', repair_parent_job_id=parent_job)
        manager._jobs[job] = value; manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)


def retry(manager, request):
    repair = request['repair_execution']
    store = manager.character_manager().application.store
    files = store.read(repair['draft']['material_bundle_sha256'])
    return submit(manager, repair['parent_job_id'], dict(request=json.loads(files['request.json']),
        view_pose=json.loads(files['view-pose.json']), png_base64=base64.b64encode(files['view.png']).decode('ascii')))
