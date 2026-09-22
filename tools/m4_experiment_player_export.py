"""Export a live player for a verified isolated Runtime capture, without adoption."""
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.sleeve_capture_environment import discover


def export(folder):
    report=json.loads((folder/'report.json').read_bytes())
    runtime=json.loads((folder/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=report['candidate_bundle_sha256'] or runtime['passed'] is not True:
        raise ValueError('experiment_player_capture_mismatch')
    files=AnimatedStore(folder/'isolated-store').read(report['candidate_bundle_sha256'])
    env=discover(Path.cwd().parent)
    if not env:raise ValueError('experiment_player_runtime_missing')
    package=Path(env[1])/'node_modules/@esotericsoftware/spine-webgl'
    raw=(package/'dist/iife/spine-webgl.js').read_bytes()
    if sha256(raw).hexdigest()!=runtime['runtime_sha256']:
        raise ValueError('experiment_player_runtime_mismatch')
    root=folder/'runtime';assets=root/'player-assets';assets.mkdir(exist_ok=False)
    web=Path('web')
    (root/'player.html').write_bytes((web/'character-player.html').read_bytes())
    for target,source in [('client.js','character-player.js'),('style.css','character-player.css'),('inspection.js','character-player-inspection.js')]:
        (assets/target).write_bytes((web/source).read_bytes())
    (assets/'runtime.js').write_bytes(raw)
    scene=dict(artifact_sha256=report['candidate_bundle_sha256'],info=runtime['info'],
        skeleton=json.loads(files['skeleton.json']),atlas=files['skeleton.atlas'].decode(),
        textures={k:'data:image/png;base64,'+b64encode(v).decode() for k,v in files.items() if k.endswith('.png')})
    (assets/'scene.json').write_text(json.dumps(scene),encoding='utf-8')
