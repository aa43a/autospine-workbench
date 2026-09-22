"""Capture bend-gated local UV overlays without adopting the material hypothesis."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from m4_squat_stage_players import stage
from m4_experiment_player_export import export
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.pose_material_overlay import build


def finish(source,output,digest):
    report=json.loads((output/'probe.json').read_bytes())
    runtime=json.loads((source/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=report['parent']:raise ValueError('pose_material_camera_identity')
    path=output/'overlay/runtime/player-assets/scene.json';scene=json.loads(path.read_bytes())
    scene['info']=runtime['info'];path.write_text(json.dumps(scene),encoding='utf-8')
    report.update(candidate=digest,shared_camera=runtime['info'])
    captured=json.loads((output/'overlay/runtime/report.json').read_bytes())
    geometry=json.loads((output/'overlay/runtime/deformation.json').read_bytes())
    old_setup=(source/'runtime/setup-frame.png').read_bytes()
    new_setup=(output/'overlay/runtime/setup-frame.png').read_bytes()
    report.update(runtime_numeric_passed=captured['passed'],runtime_samples=len(captured['results']),
                  geometry_passed=geometry['passed'],setup_identical_bytes=old_setup==new_setup,
                  setup_frame_sha256=sha256(new_setup).hexdigest())
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(candidate=digest,records=[dict(slot=r['slot'],triangles=r['triangle_count'],
          maximum_alpha=max(k['value'] for k in r['alpha_keys'])) for r in report['records']])))


def resume(source,output):
    folder=output/'overlay';receipt=json.loads((folder/'report.json').read_bytes());digest=receipt['candidate_bundle_sha256']
    captured=capture(SimpleNamespace(workspace_root=Path.cwd().parent),AnimatedStore(folder/'isolated-store'),digest,folder,
            progress=lambda s:print(s,flush=True),cancel_requested=lambda:False,storage_reference=True)
    receipt['runtime_status']=captured['status']
    (folder/'report.json').write_text(json.dumps(receipt),encoding='utf-8')
    export(folder);finish(source,output,digest)


def run(source,uv_source,output):
    receipt=json.loads((source/'report.json').read_bytes());parent=receipt['candidate_bundle_sha256']
    uv=json.loads((uv_source/'probe.json').read_bytes())
    if uv['parent']!=parent:raise ValueError('pose_material_parent')
    files=AnimatedStore(source/'isolated-store').read(parent)
    variant=AnimatedStore(uv_source/'uv/isolated-store').read(uv['candidate'])
    original=json.loads(files['skeleton.json']);alternative=json.loads(variant['skeleton.json'])
    end=1.866667
    times=sorted(set([round(i/60,9) for i in range(113) if i/60<end]+[end]))
    doc,evidence=build(original,alternative,uv['records'],times)
    output.mkdir(parents=True,exist_ok=False)
    (output/'probe.json').write_text(json.dumps(dict(parent=parent,**evidence),indent=2),encoding='utf-8')
    digest=stage(doc,files,times,output/'overlay',parent)
    finish(source,output,digest)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','uv_source','output'):p.add_argument(name,type=Path)
    p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.resume:resume(a.source,a.output)
    else:run(a.source,a.uv_source,a.output)
