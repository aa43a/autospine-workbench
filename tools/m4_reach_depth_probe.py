"""Audit source-view-consistent depth on exact shoulder candidates without adoption."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_depth import build
from autospine_workbench.targets.character43.motion_depth_overlap import inspect


def run(root,output):
    output.mkdir(parents=True,exist_ok=False);summary=[]
    inventory=json.loads((root/'comparison.json').read_bytes())
    for i,item in enumerate(inventory['rows']):
        folder=root/str(i);r=json.loads((folder/'report.json').read_bytes())
        pose=json.loads((root.parent/str(i)/'yaw-45/pose/report.json').read_bytes())
        identity=pose['source_identity'];yaw=pose['fixed_source_yaw_deg']
        if item['views'][1]['artifact']!=r['candidate_bundle_sha256'] or item['views'][1]['yaw']!=yaw:
            raise ValueError('reach_depth_view_identity_mismatch')
        files=AnimatedStore(folder/'isolated-store').read(r['candidate_bundle_sha256'])
        document=json.loads(files['skeleton.json'])
        bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
        kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
        bvh=None if kimodo else parse_bvh(bundle.raw_bvh)
        mapping=bundle.kimodo_map if kimodo else bundle.bvh_map
        correct=build(document,bvh,mapping,kimodo=kimodo,yaw_degrees=yaw)
        wrong=build(document,bvh,mapping,kimodo=kimodo,yaw_degrees=0)
        changed=sum(a['current_front_slot']!=b['current_front_slot'] or a['ambiguous']!=b['ambiguous']
                    for p,q in zip(correct['pairs'],wrong['pairs']) for a,b in zip(p['samples'],q['samples']))
        print(json.dumps(dict(character=item['label'],stage='native_alpha_overlap',view_changes=changed)),flush=True)
        report,_=inspect(document,files,'external-motion',correct,sparse='tight_triangle_boxes')
        report.update(candidate_bundle_sha256=r['candidate_bundle_sha256'],source_identity=identity,
            view_scope=pose['view_scope'],zero_yaw_comparison_changed_pair_samples=changed,
            selected=False,authority='none')
        (output/(str(i)+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        summary.append(dict(character=item['label'],candidate=r['candidate_bundle_sha256'],yaw=yaw,
            status=report['status'],groups=report['groups'],target_overlap=report['target_overlap'],
            zero_yaw_comparison_changed_pair_samples=changed))
        (output/'summary.json').write_text(json.dumps(dict(authority='none',selected=False,rows=summary),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary[-1],ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.root,a.output)
