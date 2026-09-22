"""Capture source/support stages and compare them with an exact existing candidate."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
from types import SimpleNamespace
from m4_direction_stage_probe import load_stages
from m4_experiment_player_export import export
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write


def shared_camera(output,names=('source','support','final')):
    paths=[output/name/'runtime/player-assets/scene.json' for name in names]
    scenes=[json.loads(p.read_bytes()) for p in paths];infos=[s['info'] for s in scenes]
    left=math.floor(min(i['left'] for i in infos));bottom=math.floor(min(i['bottom'] for i in infos))
    width=math.ceil(max(i['left']+i['width'] for i in infos))-left
    height=math.ceil(max(i['bottom']+i['height'] for i in infos))-bottom
    if not 0<width<=4096 or not 0<height<=4096:raise ValueError('stage_camera_bounds')
    camera=dict(left=left,bottom=bottom,width=width,height=height)
    for path,scene in zip(paths,scenes):
        scene['info'].update(camera);path.write_bytes(canonical_bytes(scene))
    return camera


def stage(document,files,times,folder,parent):
    folder.mkdir()
    raw=canonical_bytes(document);digest=sha256(raw).hexdigest()
    setup=sample(dict(document,animations={'setup':{}}),'setup',0)[0]
    result={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','character-manifest.json')}
    result['skeleton.json']=raw
    result['rig-setup-reference.json']=canonical_bytes(dict(skeleton_sha256=digest,time=0,vertices=setup))
    result=write(result,dict(skeleton_sha256=digest,animations={'external-motion':[
        dict(time=t,vertices=sample(document,'external-motion',t)[0]) for t in times]}))
    store=AnimatedStore(folder/'isolated-store');artifact=store.publish(result)
    report=dict(authority='none',selected=False,candidate_bundle_sha256=artifact,
                parent_sha256=parent,stage=folder.name,frames=len(times),scope='diagnostic_stage_not_repair_or_visual_acceptance')
    (folder/'report.json').write_bytes(canonical_bytes(report))
    captured=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,artifact,folder,
                     progress=lambda s:print(json.dumps(dict(stage=folder.name,progress=s)),flush=True),
                     cancel_requested=lambda:False,storage_reference=True)
    report['runtime_status']=captured['status']
    (folder/'report.json').write_bytes(canonical_bytes(report));export(folder)
    return artifact


def run(source,output):
    receipt=json.loads((source/'report.json').read_bytes())
    fitted,_,pose,_,_,parent,_=load_stages(receipt['source_job_id'])
    if parent!=receipt['source_candidate_sha256']:raise ValueError('squat_stage_parent_mismatch')
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    final=json.loads(files['skeleton.json'])
    if {k:v for k,v in fitted.items() if k!='animations'}!={k:v for k,v in final.items() if k!='animations'}:
        raise ValueError('squat_stage_rig_mismatch')
    runtime=json.loads((source/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=receipt['candidate_bundle_sha256'] or runtime['passed'] is not True:
        raise ValueError('squat_stage_runtime_mismatch')
    output.mkdir(parents=True,exist_ok=False)
    times=sorted(set(pose['times'])|{(a+b)/2 for a,b in zip(pose['times'],pose['times'][1:])})
    supported=deepcopy(final)
    supported['animations']['external-motion'].pop('attachments',None)
    supported['animations']['external-motion'].pop('deform',None)
    stages=[]
    for label,document in [('source',fitted),('support',supported)]:
        address=stage(document,files,times,output/label,receipt['candidate_bundle_sha256'])
        stages.append((label,address))
    if not (source/'runtime/player-assets').exists():export(source)
    target=output/'final/runtime';target.mkdir(parents=True)
    shutil.copy2(source/'runtime/player.html',target/'player.html')
    shutil.copytree(source/'runtime/player-assets',target/'player-assets')
    camera=shared_camera(output)
    rows=[]
    for label,address in stages:
        def view(name,artifact):
            evidence=source if name=='final' else output/name
            geometry=json.loads((evidence/'runtime/deformation.json').read_bytes())
            return dict(url=f'{name}/runtime/player.html',artifact=artifact,
                        geometry_passed=geometry['passed'],runtime_status='numeric_passed',unreliable_samples='未统计')
        rows.append(dict(label='源投影 → 最终候选' if label=='source' else '支撑后未修网格 → 最终候选',
                         views=[view(label,address),view('final',receipt['candidate_bundle_sha256'])]))
    comparison=dict(selected=False,title='Squat：源姿态、支撑与网格修正分阶段对照',
        headings=['所选中间阶段','当前实验候选（非新修复）'],
        note='诊断中间阶段故意保留变形和接触问题。左侧新捕获源帧及中点；右侧复用精确候选既有 Runtime 证据。数值通过不代表视觉通过。',rows=rows)
    (output/'comparison.json').write_bytes(canonical_bytes(comparison))
    for source_name,target_name in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:
        shutil.copy2(Path('tools')/source_name,output/target_name)
    page=output/'index.html'
    page.write_text(page.read_text(encoding='utf-8').replace('角色 <select','对照阶段 <select').replace('Reach 同步视角实验','Squat 阶段对照'),encoding='utf-8')
    (output/'provenance.json').write_bytes(canonical_bytes(dict(source_receipt=receipt,source_times=times,
        shared_player_camera=camera,
        final_runtime_report_sha256=sha256((source/'runtime/report.json').read_bytes()).hexdigest(),stages=stages)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.source,a.output)
