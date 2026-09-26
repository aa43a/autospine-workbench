"""Append-only related candidates, with exact playback and diagnostic downloads."""
import json
import re
from types import SimpleNamespace
from .animated_store import AnimatedStore
from .motion_related_evidence import inspect
from .storage_io import canonical_bytes, directory, publish_document, read_document
from ..resolved_project import canonical_sha256


def entries(folder):
    root=folder/'related-candidates'
    if not root.exists():return []
    directory(root);paths=sorted(root.glob('*.json'))
    if len(paths)>24:raise ValueError('motion_related_limit')
    result=[]
    for path in paths:
        if not re.fullmatch('[a-f0-9]{64}',path.stem) or read_document(path)!={'digest':path.stem}:
            raise ValueError('motion_related_registration_invalid')
        result.append(path.stem)
    return result


def baseline(manager,job):
    current=manager.get(job)
    if current.get('kind')!='adapt' or current.get('status')!='succeeded':
        raise ValueError('motion_related_baseline_unavailable')
    return current['result']['artifact_sha256']


def register(manager,job,files,receipt,runtime,visual=None):
    folder=manager.folder(job);request=read_document(folder/'request.json')
    original=baseline(manager,job);store=AnimatedStore(manager.state_root)
    evidence=inspect(request,store.read(request['character_sha256']),files,receipt,runtime,visual)
    candidate=store.publish(files)
    value=dict(baseline_sha256=original,request_sha256=canonical_sha256(request),
        candidate_sha256=candidate,evidence=evidence,receipt=receipt,runtime=runtime,visual=visual)
    digest=store.publish({'related.json':canonical_bytes(value)})
    with manager._lock:
        if baseline(manager,job)!=original or read_document(folder/'request.json')!=request:
            raise ValueError('motion_related_baseline_changed')
        old=entries(folder)
        if digest not in old and len(old)>=24:raise ValueError('motion_related_limit')
        root=directory(folder/'related-candidates',create=True)
        publish_document(root/(digest+'.json'),{'digest':digest},staging=folder/'staging')
    return digest


def load(manager,job,digest):
    folder=manager.folder(job)
    if digest not in entries(folder):raise ValueError('motion_related_unregistered')
    store=AnimatedStore(manager.state_root)
    value=json.loads(store.read_file(digest,'related.json'))
    request=read_document(folder/'request.json')
    if value['baseline_sha256']!=baseline(manager,job) or value['request_sha256']!=canonical_sha256(request):
        raise ValueError('motion_related_baseline_changed')
    files=store.read(value['candidate_sha256'])
    evidence=inspect(request,store.read(request['character_sha256']),files,
                     value['receipt'],value['runtime'],value['visual'])
    if evidence!=value['evidence']:raise ValueError('motion_related_evidence_changed')
    return value,files


def download(value,files):
    from .motion_related_export import package
    return package(value,files)


def read(manager,job,parts):
    if parts==['related-candidates.json']:
        rows=[]
        for digest in entries(manager.folder(job)):
            value,_=load(manager,job,digest)
            rows.append(dict(registration_sha256=digest,**value['evidence']))
        return canonical_bytes(dict(rows=rows,baseline_sha256=baseline(manager,job),authority='none')),'application/json'
    if len(parts)<3 or parts[0]!='related-candidates':raise ValueError('motion_related_path_invalid')
    value,files=load(manager,job,parts[1]);tail=parts[2:]
    if tail==['report.json']:return canonical_bytes(value['evidence']),'application/json'
    if tail==['candidate.zip']:return download(value,files),'application/zip'
    from .character_player import read as player
    result=dict(artifact_sha256=value['candidate_sha256'])
    adapter=SimpleNamespace(projects=manager.projects,
        review_context=lambda *_:(result,files,canonical_bytes(value['runtime'])))
    raw,mime=player(adapter,None,None,tail)
    if tail==['player.html']:
        raw=raw.replace(b'href="index.html"',b'href="report.json"')
        raw=raw.replace(b'href="setup/index.html"',b'href="report.json"')
    return raw,mime
