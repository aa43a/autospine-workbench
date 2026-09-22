"""Bake existing shoulder boundary constraints on exact isolated reach candidates."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.shoulder_boundary_candidate import generate
from autospine_workbench.targets.character43.shoulder_boundary_adaptive import generate as adapt
from m4_experiment_player_export import export


def run(root,output):
    output.mkdir(parents=True,exist_ok=False)
    comparisons=[]
    inventory=json.loads((root/'comparison.json').read_bytes())
    for index,item in enumerate(inventory['rows']):
        folder=root/str(index)/'yaw-45';target=output/str(index);target.mkdir()
        original=json.loads((folder/'mesh/report.json').read_bytes())
        pose=json.loads((folder/'pose/report.json').read_bytes())
        files=AnimatedStore(folder/'mesh/isolated-store').read(original['candidate_bundle_sha256'])
        source=AnimatedStore('workspace').read(pose['character_sha256'])
        doc=json.loads(files['skeleton.json']);setup=json.loads(source['skeleton.json'])
        if {k:v for k,v in doc.items() if k!='animations'}!={k:v for k,v in setup.items() if k!='animations'}:
            raise ValueError('reach_shoulder_setup_changed')
        files['character-manifest.json']=source['character-manifest.json']
        points=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
        files['rig-setup-reference.json']=canonical_bytes(dict(time=0,vertices=points,skeleton_sha256=sha256(files['skeleton.json']).hexdigest()))
        store=AnimatedStore(target/'isolated-store');parent=store.publish(files)
        progress=lambda message:print(json.dumps(dict(character=index,stage=message)),flush=True)
        candidate,report=generate(files,parent,progress=progress)
        trial=store.publish(candidate)
        if report['status']=='blocked':
            candidate,report=adapt(files,parent,candidate,trial,progress=progress)
        digest=store.publish(candidate)
        report.update(candidate_bundle_sha256=digest,source_candidate_sha256=original['candidate_bundle_sha256'],
            enriched_source_sha256=parent,source_rig_sha256=pose['character_sha256'])
        (target/'report.json').write_bytes(canonical_bytes(report))
        result=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,target,
            progress=progress,cancel_requested=lambda:False,storage_reference=True)
        report['runtime_status']=result['status'];(target/'report.json').write_bytes(canonical_bytes(report))
        export(target)
        left=dict(item['views'][1],url='../'+item['views'][1]['url'])
        right=dict(yaw=45,url=str(index)+'/runtime/player.html',artifact=digest,
            geometry_passed=report['geometry_passed'],runtime_status=report['runtime_status'],unreliable_samples=0)
        comparisons.append(dict(job=item['job'],label=item.get('label',item['job']),views=[left,right]))
        print(json.dumps(dict(character=index,status=report['status'],geometry=report['geometry_passed'],
            runtime=report['runtime_status'],boundary=report['dense_boundary'])),flush=True)
    data=dict(authority='none',selected=False,rows=comparisons,
        title='Reach：肩部连接修正前后同步对照',headings=['偏转 +45° · 原候选','偏转 +45° · 肩部连接候选'],
        note='两侧采用相同肢体投影，右侧只增加源接触支持的肩部变形；躯干与素材未整体转为侧视。边界数值不代替透明接缝、遮挡和视觉验收。')
    (output/'comparison.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for source,target in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:
        (output/target).write_bytes((Path('tools')/source).read_bytes())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.root,a.output)
