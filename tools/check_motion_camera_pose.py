"""Read real bound assets and exercise the shared camera/target solver offline."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_camera_pose import prepare, fit
from autospine_workbench.targets.character43.motionir_candidate import build, sample


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--character-job',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root='http://127.0.0.1:8918'
    read=lambda path:json.loads(urlopen(root+path,timeout=30).read())
    source=read('/api/motions/'+args.source)
    address=source['result']['motion']
    bundle=VerifiedMotionBundleReader(args.state).load(address['clip_sha256'],address['bundle_sha256'])
    context=read(f'/api/projects/{args.project}/automation/character/jobs/{args.character_job}/view/player-assets/context.json')
    files=AnimatedStore(args.state).read(context['artifact_sha256'])
    base=json.loads(files['skeleton.json']);base['animations']={}
    duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    args.output.mkdir(parents=True,exist_ok=False)
    from autospine_workbench.automation.motion_editor_source import build as editor_source
    data=editor_source(bundle,json.loads((bundle.path/'map.json').read_bytes()))
    (args.output/'editor-source.json').write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    (args.output/'base-skeleton.json').write_text(json.dumps(base,allow_nan=False),encoding='utf-8')
    rows=[]
    runtime_reference={}
    for name,keys in [('fixed',[{'time':0,'yaw':30}]),
                      ('turn',[{'time':0,'yaw':0},{'time':duration,'yaw':360}])]:
        motion,view,camera=prepare(bundle,keys)
        document,_=build(base,motion,'camera-preview')
        document,evidence=fit(document,'camera-preview',motion,view,camera)
        # Verify deterministic seeking including a reverse seek and final pose.
        poses=[sample(document,'camera-preview',time)[0] for time in (0,duration/2,duration,0)]
        from autospine_workbench.targets.character43.affine_pose import matrices
        runtime_reference[name]=[dict(time=time,bones=matrices(document,'camera-preview',time))
                                 for time in (0,duration/2,duration)]
        assert poses[0]==poses[-1]
        assert {k:v for k,v in document.items() if k!='animations'}=={k:v for k,v in base.items() if k!='animations'}
        fixed_error=None
        if name=='fixed':
            from autospine_workbench.automation.motion_view_pose import prepare as legacy_prepare
            from autospine_workbench.automation.motion_target_pose import project as legacy_fit
            original,old_view,old_pose=legacy_prepare(bundle,30)
            old_document,_=build(base,original,'camera-preview')
            old_document,_=legacy_fit(old_document,'camera-preview',original,None,None,None,old_view,None,old_pose)
            fixed_error=0
            for time,current in zip((0,duration/2,duration,0),poses):
                expected=sample(old_document,'camera-preview',time)[0]
                fixed_error=max(fixed_error,max(abs(a-b) for slot,points in current.items()
                    for p,q in zip(points,expected[slot]) for a,b in zip(p,q)))
            assert fixed_error<1e-8
        for file,value in [('camera',camera),('skeleton',document),('evidence',evidence)]:
            (args.output/f'{name}-{file}.json').write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        rows.append(dict(name=name,camera_sha256=camera['projection_sha256'],
                         pose_sha256=evidence['output_sha256'],frames=len(camera['times']),
                         unreliable_samples=len(camera['issues']),surface_samples=len(camera['surface_issues']),
                         maximum_direction_error=max(r['maximum_direction_error_deg'] for r in evidence['records']),
                         fixed_reference_vertex_error_px=fixed_error,
                         maximum_hip_error=evidence['hip_center']['maximum_after_error_px']))
    report=dict(source_job=args.source,source=address,character_job=args.character_job,
                character_artifact=context['artifact_sha256'],rows=rows,
                scope='raw_pose_solver_only_no_geometry_repair_contact_depth_runtime_or_visual_acceptance')
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'runtime-reference.json').write_text(json.dumps(runtime_reference,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
