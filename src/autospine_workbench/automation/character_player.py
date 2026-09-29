"""Live inspection of an exact reviewed bundle without rewriting captured evidence."""
from hashlib import sha256
from base64 import b64encode
from pathlib import Path
import json
from .pipeline_run import PipelineRunError
from .sleeve_capture_environment import discover


def read(manager, project, job, parts):
    web = Path(__file__).resolve().parents[3]/'web'
    if parts == ['player.html']:
        return (web/'character-player.html').read_bytes(), 'text/html; charset=utf-8'
    if len(parts) < 2 or parts[0] != 'player-assets':
        raise PipelineRunError('pipeline_artifact_not_found')
    name = '/'.join(parts[1:])
    if any(p in {'', '.', '..'} for p in parts[1:]):
        raise PipelineRunError('pipeline_artifact_not_found')
    if name == 'inspection.js':
        return (web/'character-player-inspection.js').read_bytes(), 'text/javascript'
    if name in {'client.js', 'style.css'}:
        filename = 'character-player.' + ('js' if name == 'client.js' else 'css')
        return (web/filename).read_bytes(), 'text/javascript' if name.endswith('.js') else 'text/css'
    load = getattr(manager, 'player_context', manager.review_context)
    result, files, raw = load(project, job)
    report = json.loads(raw)
    if report.get('bundle_sha256') != result['artifact_sha256']:
        raise PipelineRunError('character_review_source_mismatch')
    if name == 'scene.json':
        atlas = files['skeleton.atlas'].decode()
        # Only atlas pages are loaded by the player. Editor/source copies remain
        # in the verified download, but must not be base64 encoded a second time.
        pages = set()
        previous = ''
        for line in atlas.splitlines():
            current = line.strip()
            if not previous and current.endswith('.png'):
                pages.add(current)
            previous = current
        if not pages or any(page not in files for page in pages):
            raise PipelineRunError('character_player_texture_missing')
        value=dict(artifact_sha256=result['artifact_sha256'],info=report['info'],
                   skeleton=json.loads(files['skeleton.json']),atlas=atlas,
                   textures={key:'data:image/png;base64,'+b64encode(files[key]).decode()
                             for key in sorted(pages)})
        return json.dumps(value).encode(), 'application/json'
    if name == 'context.json':
        return json.dumps(dict(artifact_sha256=result['artifact_sha256'], info=report['info'],
                               runtime_sha256=report['runtime_sha256'])).encode(), 'application/json'
    if name == 'runtime.js':
        options = discover(manager.projects.workspace_root)
        if not options:
            raise PipelineRunError('character_runtime_environment_missing')
        package = Path(options[1])/'node_modules/@esotericsoftware/spine-webgl'
        metadata = json.loads((package/'package.json').read_bytes())
        runtime = (package/'dist/iife/spine-webgl.js').read_bytes()
        if (metadata.get('version') != report.get('runtime_version')
                or metadata.get('name') != report.get('runtime_package')
                or sha256(runtime).hexdigest() != report['runtime_sha256']):
            raise PipelineRunError('character_player_runtime_mismatch')
        return runtime, 'text/javascript'
    if name not in files or not (name in {'skeleton.json', 'skeleton.atlas'} or name.endswith('.png')):
        raise PipelineRunError('pipeline_artifact_not_found')
    mime = 'image/png' if name.endswith('.png') else 'application/json' if name.endswith('.json') else 'text/plain'
    return files[name], mime
