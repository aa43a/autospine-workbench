"""Source-bound target jobs and playback; never replace a reviewed character."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
from threading import Event
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .character_capture import review_name
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


def assert_current(manager, request):
    source = manager.get(request['source_job_id'])
    if canonical_sha256(source) != request['source_job_sha256']:
        raise PipelineRunError('motion_target_source_changed')
    raw = read_real_file(manager.folder(source['job_id']) / ('source.' + source['format']), 64 << 20, 'motion source')
    if sha256(raw).hexdigest() != source['source_sha256']:
        raise PipelineRunError('motion_source_changed')
    characters = manager.character_manager()
    value = characters.get(request['project_id'], request['character_job_id'])
    if value.get('status') != 'needs_review' or value.get('artifact_sha256') != request['character_sha256']:
        raise PipelineRunError('motion_target_character_changed')


def submit(manager, source_job, body):
    if (set(body) - {'project_id', 'character_job_id', 'contact_correction', 'clip', 'projection', 'projection_selection', 'depth_review_profile', 'torso_projection_profile', 'pose_profile', 'moving_ankle_profile'}
            or not {'project_id', 'character_job_id'} <= set(body)
            or type(body.get('contact_correction', True)) is not bool):
        raise PipelineRunError('motion_request_invalid')
    source = manager.get(source_job)
    from .motion_ankle_policy import select as select_ankles
    ankle_profile = select_ankles(body)
    from .motion_pose_policy import select as select_pose
    pose_profile = select_pose(body)
    from .motion_depth_policy import select as select_depth
    depth_profile = select_depth(body, source)
    from .motion_torso_policy import select as select_torso
    torso_profile = select_torso(body, depth_profile)
    if 'projection' in body:
        from ..targets.character43.oblique_target import validate
        try: validate(body['projection'])
        except ValueError as exc: raise PipelineRunError(str(exc)) from exc
    if (source.get('kind', 'import') not in ('import', 'generate') or source.get('status') != 'succeeded'
            or source.get('result', {}).get('motion_status') != 'compiled'):
        raise PipelineRunError('motion_target_source_unavailable')
    if body.get('clip') is not None:
        from ..targets.character43.motion_clip import validate
        try:
            validate(body['clip'], source['result']['frame_count'])
        except (ValueError, KeyError):
            raise PipelineRunError('motion_clip_range_invalid') from None
    characters = manager.character_manager()
    project, character_job = body['project_id'], body['character_job_id']
    character, _ = characters.verified_snapshot(project, character_job)
    from ..targets.character43.runtime_storage_reference import PROFILE
    from ..targets.character43.phase_contact_policy import PROFILE as CONTACT_PROFILE
    request = dict(kind='adapt', source_job_id=source_job, source_job_sha256=canonical_sha256(source),
                   motion_identity=source['result']['motion'], project_id=project, character_job_id=character_job,
                   character_sha256=character['artifact_sha256'], name=source['name'],
                   contact_correction=body.get('contact_correction', True), runtime_reference_profile=PROFILE,
                   inferred_contact_profile=CONTACT_PROFILE, depth_review_profile=depth_profile)
    if body.get('clip') is not None:
        request['clip'] = body['clip']
    from ..targets.character43.motion_depth_overlap import SPARSE_DEPTH_PROFILE
    if depth_profile in ('external-arm-torso-depth-overlap-v2',SPARSE_DEPTH_PROFILE):
        from ..targets.character43.local_depth_analysis import PROFILE as LOCAL_PROFILE
        request['local_depth_profile']=LOCAL_PROFILE
    if torso_profile is not None:
        request['torso_projection_profile'] = torso_profile
    if pose_profile is not None:
        request['pose_profile'] = pose_profile
    if ankle_profile is not None:
        request['moving_ankle_profile'] = ankle_profile
    if 'projection' in body:
        request['projection'] = dict(body['projection'])
    if 'projection_selection' in body:
        from .motion_oblique_comparison import validate_selection
        try:
            request['projection_selection'] = validate_selection(manager,source_job,body['projection_selection'],body.get('projection'))
        except ValueError as exc: raise PipelineRunError(str(exc)) from exc
    assert_current(manager, request)
    with manager._lock:
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-' + uuid4().hex
        root = manager.folder(job, True)
        request['job_id'] = job
        publish_document(root / 'request.json', request, staging=root / 'staging')
        value = dict(job_id=job, kind='adapt', project_id=project, character_job_id=character_job,
                     name=source['name'], status='pending', step='queued', authority='none')
        manager._jobs[job] = value
        manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)


def context(manager, job):
    value = manager.get(job)
    if value.get('kind') != 'adapt' or value['status'] != 'succeeded':
        raise PipelineRunError('motion_preview_unavailable')
    result = value['result']
    store = manager.character_manager().application.store
    files = store.read(result['artifact_sha256'])
    return result, files


def runtime_reader(manager, job, result):
    """Read captures against this request's verified candidate inventory."""
    def read(name):
        name = review_name(name)
        expected = result.get('runtime', {}).get('files', {}).get(name)
        if not expected:
            raise PipelineRunError('pipeline_artifact_not_found')
        root = directory(manager.folder(job) / 'runtime')
        directory((root / name).parent)
        raw = read_real_file(root / name, 64 << 20, 'motion runtime')
        if sha256(raw).hexdigest() != expected:
            raise PipelineRunError('pipeline_artifact_invalid')
        return raw
    return read


def review_file(manager, job, parts):
    if parts == ['related-candidates.json'] or parts[:1] == ['related-candidates']:
        from .motion_related_candidates import read
        return read(manager, job, parts)
    if parts[:1] == ['pose-geometry']:
        from .motion_pose_geometry_editor import read
        return read(manager, job, parts)
    if parts == ['experiments.json'] or parts[:1] == ['experiments']:
        from .motion_experiments import read
        return read(manager, job, parts)
    if (parts == ['player.html'] or len(parts) == 2 and parts[0] == 'player-assets'
            and parts[1] in ('client.js', 'style.css', 'inspection.js')):
        from .character_player import read
        # These are static application assets. Actual scene and runtime reads below
        # still verify the addressed job, character sources and capture inventory.
        return read(None, None, None, parts)
    result, files = context(manager, job)
    if parts[:1] == ['contact-scope']:
        from .motion_contact_preflight import read
        return read(manager, job, parts, result, files)
    runtime_file = runtime_reader(manager, job, result)
    if parts == ['repair-summary.json']:
        if 'motion-repair.json' not in files:
            raise PipelineRunError('pipeline_artifact_not_found')
        repair = json.loads(files['motion-repair.json'])
        parent = json.loads(files['motion-repair-provenance.json'])
        report = dict(artifact_sha256=result['artifact_sha256'], parent_job_id=parent['parent_job_id'],
            parent_artifact_sha256=parent['parent_artifact_sha256'], slot=repair['slot'],
            before=repair.get('parent_geometry'), after=repair['geometry'],
            unchanged_other_channels=repair.get('unchanged_other_channels',True),
            profile=repair['profile'],boundary=repair.get('boundary'), material=repair.get('material'), selected=False, authority='none')
        if report['before'] is None:
            report['before'] = dict(passed=None, records=[], status='unavailable')
        if repair.get('region_order'):
            report['region_order'] = repair['region_order']
        if 'view-pose-report.json' in files:
            variant = json.loads(files['view-pose-report.json'])['variant']
            report['additional_view'] = {k: variant[k] for k in (
                'original_attachment', 'variant_attachment', 'interval', 'runtime_interval')}
            report['additional_view']['switch_continuity'] = repair.get('switch_continuity')
        if 'pose-geometry-report.json' in files:
            patch = json.loads(files['pose-geometry-report.json'])
            poses = json.loads(files['pose-geometry-request.json'])
            report['pose_geometry'] = dict(interval=patch['interval'], vertices=len(patch['vertices']),
                times=[p['time'] for p in poses['poses']], authored_point_error_px=patch['authored_point_error_px'],
                unchanged_vertex_error_px=patch['unchanged_vertex_error_px'],
                outside_interval_error_px=patch['outside_interval_error_px'])
        return json.dumps(report,ensure_ascii=False).encode('utf-8'),'application/json'
    if parts == ['source-comparison.json']:
        from .motion_source_comparison import build
        return json.dumps(build(manager, job, result), ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json'
    if parts == ['final-contact.json']:
        from ..targets.character43.final_motion_contact import for_candidate
        report = for_candidate(files, result['artifact_sha256'], json.loads(runtime_file('report.json')))
        return json.dumps(report, ensure_ascii=False).encode('utf-8'), 'application/json'
    if parts == ['motion-review.json']:
        if 'motion-review.json' not in files:
            raise PipelineRunError('pipeline_artifact_not_found')
        return files['motion-review.json'], 'application/json'
    if parts == ['bend-status.json']:
        from ..motion_bundle_reader import VerifiedMotionBundleReader
        from ..targets.character43.knee_projection import build
        request=read_document(manager.folder(job)/'request.json');identity=request['motion_identity']
        bundle=VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'],identity['bundle_sha256'])
        return json.dumps(build(files,result['artifact_sha256'],bundle,request)).encode(), 'application/json'
    if parts in (['hand-status.json'],['hand-status.html']):
        from ..motion_bundle_reader import VerifiedMotionBundleReader
        from ..targets.character43.motion_hand_status import build,render
        request=read_document(manager.folder(job)/'request.json');identity=request['motion_identity']
        bundle=VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'],identity['bundle_sha256'])
        report=build(files,result['artifact_sha256'],bundle,request)
        return ((render(report),'text/html; charset=utf-8') if parts==['hand-status.html'] else
                (json.dumps(report,ensure_ascii=False).encode('utf-8'),'application/json'))
    if parts == ['local-depth-status.json']:
        from .motion_local_depth_evidence import read
        request=read_document(manager.folder(job)/'request.json')
        return json.dumps(read(manager.state_root,manager.folder(job),request,result['artifact_sha256'],files),
                          ensure_ascii=False).encode('utf-8'),'application/json'
    if parts == ['motion-torso-projection.json']:
        if 'motion-torso-projection.json' not in files:raise PipelineRunError('pipeline_artifact_not_found')
        return files['motion-torso-projection.json'], 'application/json'
    if parts == ['rotation-status.json']:
        from ..motion_bundle_reader import VerifiedMotionBundleReader
        from ..targets.character43.motion_rotation_status import build
        request = read_document(manager.folder(job) / 'request.json')
        identity = request['motion_identity']
        bundle = VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
        return json.dumps(build(files, result['artifact_sha256'], bundle, request),
                          ensure_ascii=False).encode('utf-8'), 'application/json'
    if parts == ['depth-status.json']:
        from ..targets.character43.motion_depth_status import build
        return json.dumps(build(files,result['artifact_sha256']),ensure_ascii=False).encode('utf-8'),'application/json'
    if parts == ['motion-projection.json']:
        if 'motion-projection.json' not in files:
            raise PipelineRunError('pipeline_artifact_not_found')
        return files['motion-projection.json'], 'application/json'
    if parts == ['motion-contact.json']:
        return files['motion-contact.json'], 'application/json'
    if parts in (['depth-ownership.json'], ['depth-ownership.html']):
        if 'motion-depth.json' not in files:
            raise PipelineRunError('pipeline_artifact_not_found')
        from ..targets.character43.depth_ownership_review import build, render
        report = build(files)
        if parts == ['depth-ownership.json']:
            return json.dumps(report, ensure_ascii=False).encode('utf-8'), 'application/json'
        return render(report), 'text/html; charset=utf-8'
    if parts in (['motion-depth.json'], ['depth.html']):
        if 'motion-depth.json' not in files:
            if parts == ['depth.html'] and result.get('repair_profile'):
                return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    '<title>修复后遮挡待验证</title><h1>修复后遮挡尚未重新验证</h1>'
                    '<p>所选附件的变形已经变化，原候选的遮挡检查不能直接沿用。'
                    '此页面不表示遮挡通过；请先检查整角色动画，保留待复核状态。</p>'
                    '<a href="player.html">播放当前候选</a> · '
                    '<a href="readiness.json">当前检查状态</a></html>').encode('utf-8'), 'text/html; charset=utf-8'
            raise PipelineRunError('pipeline_artifact_not_found')
        if parts == ['motion-depth.json']:
            return files['motion-depth.json'], 'application/json'
        from ..targets.character43.motion_depth_review import render
        return render(json.loads(files['motion-depth.json'])), 'text/html; charset=utf-8'
    if parts == ['contact.html']:
        from ..targets.character43.motion_contact_review import render
        return render(json.loads(files['motion-contact.json'])), 'text/html; charset=utf-8'
    if parts == ['readiness.json']:
        from ..targets.character43.motion_readiness import build
        runtime = (json.loads(runtime_file('report.json'))
                   if result.get('runtime', {}).get('files', {}).get('report.json') else None)
        return json.dumps(build(files, result['artifact_sha256'], runtime), ensure_ascii=False).encode('utf-8'), 'application/json'
    if parts == ['geometry-details.json']:
        from .motion_geometry_cache import read
        return read(files, result['artifact_sha256']), 'application/json'
    if parts == ['repair-feasibility.json']:
        from ..targets.character43.repair_feasibility import inspect
        return json.dumps(inspect(files,result['artifact_sha256']),ensure_ascii=False,allow_nan=False).encode('utf-8'), 'application/json'
    if parts == ['partition-mesh.json']:
        from .motion_partition_draft import meshes
        return json.dumps(meshes(files,result['artifact_sha256']),ensure_ascii=False,allow_nan=False).encode('utf-8'), 'application/json'
    if parts == ['player.html'] or parts[:1] == ['player-assets']:
        from .character_player import read
        adapter = SimpleNamespace(projects=manager.projects,
                                  review_context=lambda *_: (result, files, runtime_file('report.json')))
        return read(adapter, None, None, parts)
    name = '/'.join(parts)
    raw = runtime_file(name)
    suffix = name.rsplit('.', 1)[-1]
    return raw, {'html': 'text/html; charset=utf-8', 'json': 'application/json', 'png': 'image/png'}[suffix]


def download(manager, job):
    result, files = context(manager, job)
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(ZipInfo(name, (1980, 1, 1, 0, 0, 0)), raw)
    assert_current(manager, read_document(manager.folder(job) / 'request.json'))
    return output.getvalue()
