"""Immutable, read-only experiment attachments to an exact baseline motion job."""
import json
import re
from types import SimpleNamespace
from .animated_store import AnimatedStore
from .storage_io import canonical_bytes, directory, publish_document, read_document
from ..resolved_project import canonical_sha256


def validate(request, parent, report, runtime):
    if (parent.get('job_id') != request['job_id']
            or parent.get('source_character_sha256') != request['character_sha256']
            or parent.get('motion_identity') != request['motion_identity']
            or request.get('clip') or request.get('projection')):
        raise ValueError('motion_experiment_source_mismatch')
    if (report.get('profile') != 'post-contact-source-pose-repair-v1'
            or report.get('source_candidate_sha256') != parent.get('candidate_bundle_sha256')
            or report.get('authority') != 'none' or report.get('selected') is not False
            or report.get('production_authorized') is not False):
        raise ValueError('motion_experiment_parent_mismatch')
    if (runtime.get('bundle_sha256') != report.get('candidate_bundle_sha256')
            or len(runtime.get('results', [])) != report.get('sampled_frames')
            or not runtime.get('results')):
        raise ValueError('motion_experiment_runtime_mismatch')


def entries(folder):
    journal = folder / 'motion-experiments'
    if not journal.exists(): return []
    directory(journal)
    rows = sorted(journal.glob('*.json'))
    if len(rows) > 24: raise ValueError('motion_experiment_limit')
    result = []
    for path in rows:
        value = read_document(path)
        if not re.fullmatch('[a-f0-9]{64}', path.stem) or value != {'digest': path.stem}:
            raise ValueError('motion_experiment_registration_invalid')
        result.append(path.stem)
    return result


def publish(root, folder, request, baseline, parent, report, runtime, files):
    validate(request, parent, report, runtime)
    store = AnimatedStore(root)
    artifact = store.publish(files)
    if artifact != report['candidate_bundle_sha256']:
        raise ValueError('motion_experiment_candidate_mismatch')
    value = dict(request_sha256=canonical_sha256(request), baseline_sha256=baseline,
                 parent=parent, report=report, runtime=runtime)
    digest = store.publish({'experiment.json': canonical_bytes(value)})
    old = entries(folder)
    if digest not in old and len(old) >= 24: raise ValueError('motion_experiment_limit')
    journal = directory(folder / 'motion-experiments', create=True)
    publish_document(journal / (digest + '.json'), dict(digest=digest), staging=folder / 'staging')
    return digest


def load(manager, job, digest):
    folder = manager.folder(job)
    if digest not in entries(folder): raise ValueError('motion_experiment_unregistered')
    value = json.loads(AnimatedStore(manager.state_root).read_file(digest, 'experiment.json'))
    request = read_document(folder / 'request.json')
    baseline = manager.get(job)
    if (value['request_sha256'] != canonical_sha256(request)
            or value['baseline_sha256'] != baseline.get('result', {}).get('artifact_sha256')):
        raise ValueError('motion_experiment_baseline_changed')
    validate(request, value['parent'], value['report'], value['runtime'])
    return value


def read(manager, job, parts):
    if parts == ['experiments.json']:
        rows = []
        for digest in entries(manager.folder(job)):
            value = load(manager, job, digest)
            rows.append(dict(evidence_sha256=digest, **value['report']))
        return canonical_bytes(dict(rows=rows, authority='none')), 'application/json'
    if len(parts) < 3 or parts[0] != 'experiments':
        raise ValueError('motion_experiment_path_invalid')
    value = load(manager, job, parts[1]); tail = parts[2:]
    if tail == ['report.json']:
        return canonical_bytes(value), 'application/json'
    from .character_player import read as player
    files = AnimatedStore(manager.state_root).read(value['report']['candidate_bundle_sha256'])
    result = dict(artifact_sha256=value['report']['candidate_bundle_sha256'])
    if tail in (['bend-status.json'], ['view-tradeoffs.json']):
        from ..motion_bundle_reader import VerifiedMotionBundleReader
        if tail == ['bend-status.json']:
            from ..targets.character43.knee_projection import build
        else:
            from ..targets.character43.source_view_tradeoffs import build
        request=read_document(manager.folder(job)/'request.json');identity=request['motion_identity']
        bundle=VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'],identity['bundle_sha256'])
        return canonical_bytes(build(files,result['artifact_sha256'],bundle,request)), 'application/json'
    adapter = SimpleNamespace(projects=manager.projects,
        review_context=lambda *_: (result, files, canonical_bytes(value['runtime'])))
    raw, mime = player(adapter, None, None, tail)
    if tail == ['player.html']:
        raw = raw.replace(b'<a href="index.html">', b'<a href="report.json">')
        raw = raw.replace(b'<a href="setup/index.html">', b'<a href="report.json">')
        raw = raw.replace('原始捕获帧'.encode(), '实验与捕获记录'.encode())
        raw = raw.replace('源图对照'.encode(), '来源记录'.encode())
    return raw, mime
