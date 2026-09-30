"""Opt-in real configured official Runtime capture of a fresh synthetic mesh.

All outputs live in one new caller-named test directory. No project collection,
review decision, saved environment, installer, or global tool is modified.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.character_player import read
from autospine_workbench.automation.sleeve_capture_environment import discover,identity,node_executable,runtime_core
from autospine_workbench.automation.storage_io import canonical_bytes,directory
from autospine_workbench.targets.character43.affine_pose import sample


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','dependencies','browser','node'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    root=args.output.absolute()
    if root.exists():raise ValueError('fixture_output_exists')
    directory(root.parent)
    root.mkdir()
    os.environ.update(AUTOSPINE_CAPTURE_DEPENDENCIES=str(args.dependencies.absolute()),
        AUTOSPINE_CAPTURE_BROWSER=str(args.browser.absolute()),AUTOSPINE_CAPTURE_NODE=str(args.node.absolute()))
    started=time.monotonic();workspace=root/'empty-workspace';workspace.mkdir()
    options=discover(workspace)
    before=identity(options[1],options[3])
    assert options[1]==str(args.dependencies.absolute())
    assert node_executable()==str(args.node.absolute())
    node_version=subprocess.run([node_executable(),'--version'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    core=runtime_core(workspace)
    assert core==args.dependencies.absolute()/'node_modules/@esotericsoftware/spine-core'
    document=dict(skeleton=dict(spine='4.3.26',width=16,height=16),
        bones=[dict(name='root',x=0,y=0,rotation=0)],slots=[dict(name='square',bone='root',attachment='square')],
        skins=[dict(name='default',attachments={'square':{'square':dict(type='mesh',path='square',width=16,height=16,
            uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],hull=4,
            vertices=[v for x,y in ((-8,8),(8,8),(8,-8),(-8,-8)) for v in (1,0,x,y,1)])}})],
        animations={'move':dict(bones={'root':{'translate':[dict(time=0,x=0,y=0),dict(time=.1,x=2,y=1)]}})})
    skeleton=canonical_bytes(document);png=BytesIO();Image.new('RGBA',(16,16),(255,80,60,255)).save(png,format='PNG')
    manifest=dict(authority='none',production_authorized=False,
        layers=[dict(layer_id='square',name='square',regions=[dict(region_id='square',state='weighted_mesh')])])
    reference=dict(skeleton_sha256=sha256(skeleton).hexdigest(),animations={'move':[
        dict(time=t,vertices=sample(document,'move',t)[0]) for t in (0,.05,.1)]})
    files={'skeleton.json':skeleton,'texture.png':png.getvalue(),'images/square.png':png.getvalue(),
        'skeleton.atlas':b'texture.png\nsize:16,16\nfilter:Linear,Linear\nrepeat:none\nsquare\n bounds:0,0,16,16\n',
        'character-manifest.json':canonical_bytes(manifest),'numeric-reference.json':canonical_bytes(reference)}
    store=AnimatedStore(root/'test-state');digest=store.publish(files);output=root/'capture';output.mkdir()
    stages=[]
    result=capture(SimpleNamespace(workspace_root=workspace),store,digest,output,
        progress=stages.append,cancel_requested=lambda:False)
    assert result['status']=='needs_review' and result['frames']==3 and result['geometry_status']=='passed'
    # Browser diagnostics must survive outside the strict playback inventory.
    if args.browser.name.lower() == 'chrome-headless-shell.exe':
        assert (output/'runtime-browser-debug.log').is_file()
    assert all(Path(name).suffix in {'.html','.json','.png'} for name in result['files'])
    assert not (output/'runtime/browser-debug.log').exists()
    runtime_report=(output/'runtime/report.json').read_bytes()
    manager=SimpleNamespace(projects=SimpleNamespace(workspace_root=workspace),
        review_context=lambda *_:(dict(artifact_sha256=digest),files,runtime_report))
    raw,mime=read(manager,'test-only','test-only',['player-assets','runtime.js'])
    assert mime=='text/javascript' and sha256(raw).hexdigest()==before['runtime']['dist/iife/spine-webgl.js']
    assert identity(options[1],options[3])==before
    assert store.read(digest)==files
    report=dict(ok=True,scope='configured-official-capture-and-player-synthetic-mesh-only',
        elapsed_seconds=time.monotonic()-started,node_version=node_version,frames=result['frames'],
        bundle_sha256=digest,stages=stages,environment=before,
        source_unchanged=True,environment_unchanged=True,diagnostics_outside_playback=True,
        user_state_touched=False,human_visual_acceptance=False)
    (root/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps({key:report[key] for key in ('ok','scope','elapsed_seconds','node_version','frames','source_unchanged','environment_unchanged')}))


if __name__=='__main__':main()
