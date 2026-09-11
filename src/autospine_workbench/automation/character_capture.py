"""External official capture and source-raster analysis for a unified candidate."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

from .sleeve_capture_environment import discover
from .storage_io import directory
from .pipeline_run import PipelineRunError


def review_name(name):
    if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}',name):
        raise PipelineRunError('pipeline_artifact_not_found')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in {'','.','..'} for p in name.split('/')) or path.suffix not in {'.html','.json','.png'}:
        raise PipelineRunError('pipeline_artifact_not_found')
    return name


def capture(projects, store, digest, root, *, progress, cancel_requested):
    options = discover(projects.workspace_root)
    if not options:
        return dict(status='unavailable',reason_code='character_runtime_environment_missing')
    if cancel_requested(): raise ValueError('character_build_canceled')
    dependencies, browser = options[1], options[3]
    repo = Path(__file__).resolve().parents[3]
    output = directory(root/'runtime',create=True)
    candidate=store.read(digest)  # Content inventory must pass before an external process runs.
    from ..targets.character43.deformation_qa import inspect
    from .storage_io import canonical_bytes
    geometry=inspect(candidate)
    (output/'deformation.json').write_bytes(canonical_bytes(geometry))
    progress('runtime')
    commands = [
        ['node',str(repo/'tools/capture-character-runtime.mjs'),str(store.root/digest),str(output),dependencies,browser],
        [sys.executable,str(repo/'tools/review-character-setup.py'),str(store.root/digest),str(output),str(output/'setup')],
    ]
    for index, command in enumerate(commands):
        if cancel_requested(): raise ValueError('character_build_canceled')
        with (root/f'capture-{index}.log').open('wb') as log:
            run = subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=180,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if run.returncode: raise ValueError('character_runtime_capture_failed')
    if cancel_requested(): raise ValueError('character_build_canceled')
    report = json.loads((output/'report.json').read_bytes())
    if report['bundle_sha256']!=digest or report.get('authority')!='none' or report.get('production_authorized') is not False:
        raise ValueError('character_runtime_report_source')
    files = {}
    for path in output.rglob('*'):
        if path.is_file():
            name=review_name(path.relative_to(output).as_posix())
            files[name]=sha256(path.read_bytes()).hexdigest()
    return dict(status='needs_review',scope=report['scope'],frames=len(report['results']),
                slots=report['info']['slots'],files=files,contact_status='not_evaluated',
                geometry_status='passed' if geometry['passed'] else 'needs_changes',
                geometry_failed_records=sum(not r['passed'] for r in geometry['records']))
