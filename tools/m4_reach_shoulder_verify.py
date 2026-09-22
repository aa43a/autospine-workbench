"""Verify exact reach shoulder candidates and freeze compact evidence, not acceptance."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore


def without_deforms(animation):
    result={k:v for k,v in animation.items() if k not in ('deform','attachments')}
    attachments={}
    for skin,slots in animation.get('attachments',{}).items():
        for slot,names in slots.items():
            for name,channels in names.items():
                remaining={k:v for k,v in channels.items() if k!='deform'}
                if remaining:attachments.setdefault(skin,{}).setdefault(slot,{})[name]=remaining
    if attachments:result['attachments']=attachments
    return result


def verify(root, output):
    inventory=json.loads((root/'comparison.json').read_bytes());rows=[]
    for index,item in enumerate(inventory['rows']):
        folder=root/str(index);report=json.loads((folder/'report.json').read_bytes())
        runtime=json.loads((folder/'runtime/report.json').read_bytes())
        digest=report['candidate_bundle_sha256']
        if runtime['bundle_sha256']!=digest or runtime['passed'] is not True:
            raise ValueError('shoulder_runtime_identity_or_failure')
        files=AnimatedStore(folder/'isolated-store').read(digest)
        prior=root.parent/str(index)/'yaw-45/mesh'
        source=AnimatedStore(prior/'isolated-store').read(report['source_candidate_sha256'])
        before=json.loads(source['skeleton.json']);after=json.loads(files['skeleton.json'])
        if {k:v for k,v in before.items() if k!='animations'}!={k:v for k,v in after.items() if k!='animations'}:
            raise ValueError('shoulder_setup_changed')
        for name,animation in before['animations'].items():
            if without_deforms(animation)!=without_deforms(after['animations'][name]):
                raise ValueError('shoulder_non_deform_motion_changed')
        for name,raw in source.items():
            if name.endswith(('.png','.atlas')) and files.get(name)!=raw:
                raise ValueError('shoulder_art_changed')
        if not report['geometry_passed'] or report['unselected_error_px']!=0 or report['distal_fixed_error_px']!=0:
            raise ValueError('shoulder_geometry_or_fixed_vertices_failed')
        rows.append(dict(character=item['label'],candidate=digest,
            source_candidate=report['source_candidate_sha256'],boundary=report['dense_boundary'],
            runtime_version=runtime['runtime_version'],runtime_frames=len(runtime['results']),
            geometry_passed=True,setup_and_non_deform_motion_unchanged=True,textures_unchanged=True,
            unselected_and_distal_fixed_error_px=0,visual_status='not_accepted'))
    result=dict(profile='reach-shoulder-verification-v1',authority='none',selected=False,rows=rows,
        limitations=['limb_yaw_only_not_whole_character_side_view',
                    'sampled_geometry_not_continuous_or_alpha_seam_proof',
                    'three_2.4s_images_inspected_not_full_motion_visual_acceptance'])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(verified=len(rows),output=str(output))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();verify(a.root,a.output)
