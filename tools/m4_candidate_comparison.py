"""Publish same-camera paired players only from identity-verified Runtime captures."""
import argparse
from base64 import b64decode
from hashlib import sha256
import json
from pathlib import Path
import shutil
from m4_experiment_player_export import export
from m4_squat_stage_players import shared_camera
from autospine_workbench.automation.animated_store import AnimatedStore


def run(before,after,output,title):
    sources=[before,after];rows=[]
    output.mkdir(parents=True,exist_ok=False)
    for label,folder in zip(('before','after'),sources):
        report=json.loads((folder/'report.json').read_bytes());artifact=report['candidate_bundle_sha256']
        runtime=json.loads((folder/'runtime/report.json').read_bytes())
        if runtime['bundle_sha256']!=artifact or runtime['passed'] is not True:
            raise ValueError('candidate_comparison_capture_mismatch')
        files=AnimatedStore(folder/'isolated-store').read(artifact)
        if not (folder/'runtime/player-assets').exists():export(folder)
        scene=json.loads((folder/'runtime/player-assets/scene.json').read_bytes())
        if scene['artifact_sha256']!=artifact or scene['skeleton']!=json.loads(files['skeleton.json']):
            raise ValueError('candidate_comparison_player_mismatch')
        expected={n:v for n,v in files.items() if n.endswith('.png')}
        textures=scene.get('textures',{})
        if (set(textures)!=set(expected) or scene['atlas']!=files['skeleton.atlas'].decode()
                or any(not textures[n].startswith('data:image/png;base64,')
                       or b64decode(textures[n].split(',',1)[1],validate=True)!=v for n,v in expected.items())
                or sha256((folder/'runtime/player-assets/runtime.js').read_bytes()).hexdigest()!=runtime['runtime_sha256']):
            raise ValueError('candidate_comparison_player_assets_mismatch')
        target=output/label/'runtime';target.mkdir(parents=True)
        shutil.copy2(folder/'runtime/player.html',target/'player.html')
        shutil.copytree(folder/'runtime/player-assets',target/'player-assets')
        geometry=json.loads((folder/'runtime/deformation.json').read_bytes())
        rows.append(dict(url=label+'/runtime/player.html',artifact=artifact,
                         geometry_passed=geometry['passed'],runtime_status='numeric_passed',unreliable_samples='未统计'))
    camera=shared_camera(output,('before','after'))
    data=dict(authority='none',selected=False,title=title,headings=['修正前','修正候选'],
        note='统一相机与时间；原有技术失败保留。数值通过不代表接缝、遮挡或整段视觉通过。',
        shared_camera=camera,rows=[dict(label=title,views=rows)])
    (output/'comparison.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    for source,target in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:
        shutil.copy2(Path('tools')/source,output/target)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','output'):p.add_argument(name,type=Path)
    p.add_argument('--title',required=True);a=p.parse_args();run(a.before,a.after,a.output,a.title)
