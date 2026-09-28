"""External official capture and source-raster analysis for a unified candidate."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import math

from .sleeve_capture_environment import discover
from .storage_io import directory
from .pipeline_run import PipelineRunError


def runtime_timeout(frame_count):
    """Bound work by verified reference frames; keep the historical small-run floor."""
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError('character_runtime_frame_count')
    return min(900, max(180, math.ceil(60 + frame_count*.2)))


def review_name(name):
    if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}',name):
        raise PipelineRunError('pipeline_artifact_not_found')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in {'','.','..'} for p in name.split('/')) or path.suffix not in {'.html','.json','.png'}:
        raise PipelineRunError('pipeline_artifact_not_found')
    return name


def capture(projects, store, digest, root, *, progress, cancel_requested, storage_reference=False):
    options = discover(projects.workspace_root)
    if not options:
        return dict(status='unavailable',reason_code='character_runtime_environment_missing')
    if cancel_requested(): raise ValueError('character_build_canceled')
    dependencies, browser = options[1], options[3]
    progress('runtime_prepare')
    repo = Path(__file__).resolve().parents[3]
    output = directory(root/'runtime',create=True)
    candidate=store.read(digest)  # Content inventory must pass before an external process runs.
    from ..targets.character43.static_region_review import build as static_review
    static_files, static_links = static_review(candidate)
    for name, raw in static_files.items():
        path = output/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    from ..targets.character43.deformation_qa import inspect
    from .storage_io import canonical_bytes
    setup_reference = json.loads(candidate['rig-setup-reference.json']) if 'rig-setup-reference.json' in candidate else None
    if setup_reference and setup_reference['skeleton_sha256'] != sha256(candidate['skeleton.json']).hexdigest():
        raise ValueError('character_reference_source_mismatch')
    progress('runtime_geometry')
    geometry=inspect(candidate, setup_vertices=setup_reference['vertices'] if setup_reference else None)
    if 'joint-animation.json' in candidate:
        from ..targets.character43.joint_animation_qa import geometry_report
        joint = json.loads(candidate['joint-animation.json'])
        if joint['skeleton_sha256'] != sha256(candidate['skeleton.json']).hexdigest():
            raise ValueError('joint_animation_reference_mismatch')
        provenance = json.loads(candidate['joint-provenance.json'])
        parent = provenance['parent_artifact_sha256']
        if sha256(store.read_file(parent, 'skeleton.json')).hexdigest() != joint['parent_skeleton_sha256']:
            raise ValueError('joint_animation_capture_parent_mismatch')
        geometry = geometry_report(geometry, joint['inventory']['face'], joint['config']['face']['enabled'],
            face_report=joint['face'], source_geometry=json.loads(store.read_file(parent, 'deformation.json')))
    from ..targets.character43.numeric_reference import read as read_reference
    frame_count=sum(len(frames) for frames in read_reference(candidate)['animations'].values())
    (output/'deformation.json').write_bytes(canonical_bytes(geometry))
    commands = [
        ['node',str(repo/'tools/capture-character-runtime.mjs'),str(store.root/digest),str(output),dependencies,browser],
        [sys.executable,str(repo/'tools/review-character-setup.py'),str(store.root/digest),str(output),str(output/'setup')],
    ]
    if storage_reference:
        progress('runtime_reference')
        from ..targets.character43.runtime_storage_reference import build
        storage = build(candidate)
        path = root/'runtime-storage-reference.json'
        raw = canonical_bytes(storage)
        if len(raw)>256*1024*1024:raise ValueError('runtime_storage_reference_limit')
        if len(raw)>64*1024*1024:
            import gzip
            path = root/'runtime-storage-reference.json.gz'
            raw = gzip.compress(raw,mtime=0)
        path.write_bytes(raw)
        commands[0].extend(['32', '{}', str(path)])
    for index, command in enumerate(commands):
        if cancel_requested(): raise ValueError('character_build_canceled')
        progress('runtime' if index == 0 else 'runtime_setup')
        with (root/f'capture-{index}.log').open('wb') as log:
            try:
                run = subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT,
                                     timeout=runtime_timeout(frame_count) if index==0 else 180,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired as exc:
                raise ValueError('character_runtime_timeout') from exc
        if run.returncode: raise ValueError('character_runtime_capture_failed')
    if cancel_requested(): raise ValueError('character_build_canceled')
    report = json.loads((output/'report.json').read_bytes())
    if report['bundle_sha256']!=digest or report.get('authority')!='none' or report.get('production_authorized') is not False:
        raise ValueError('character_runtime_report_source')
    if 'skirt-trial.json' in candidate:
        from ..targets.character43.skirt_review import render
        from ..targets.character43.skirt_motion_contact import analyze
        folder = directory(output/'skirt', create=True)
        contact = analyze(candidate)
        (folder/'contact.json').write_bytes(canonical_bytes(contact))
        (folder/'index.html').write_bytes(render(candidate, report, contact=contact))
    if 'component-mount.json' in candidate:
        from ..targets.character43.component_mount_review import render as render_mount
        folder=directory(output/'mount',create=True)
        (folder/'index.html').write_bytes(render_mount(candidate,report))
    files = {}
    for path in output.rglob('*'):
        if path.is_file():
            name=review_name(path.relative_to(output).as_posix())
            files[name]=sha256(path.read_bytes()).hexdigest()
    return dict(status='needs_review',scope=report['scope'],frames=len(report['results']),
                slots=report['info']['slots'],files=files,static_region_links=static_links,contact_status='not_evaluated',
                geometry_status='passed' if geometry['passed'] else 'needs_changes',
                geometry_failed_records=sum(not r['passed'] for r in geometry['records']))
