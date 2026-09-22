"""Three structural rigs, identical source times, isolated polar-skinning candidates."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices,sample
from autospine_workbench.targets.character43.deform_addition import entries,local_delta
from autospine_workbench.targets.character43.polar_skinning import solve
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_squat_stage_players import stage


def summarize(report):
    return dict(character=report['character'],parent=report['parent'],candidate=report['candidate'],
        rows=[{k:r[k]for k in ('slot','time','actual','polar','maximum_displacement_px','single_bone_shift_px')}for r in report['records']])


def run(case,output,*,shared_joint=False):
    parent=case['artifact'];files=AnimatedStore(Path('workspace')).read(parent)
    doc=json.loads(files['skeleton.json']);name='external-motion'
    raw=deepcopy(doc);raw['animations'][name].pop('attachments',None);raw['animations'][name].pop('deform',None)
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    rest=matrices(dict(doc,animations={'setup':{}}),'setup',0)
    duration=max(k['time']for tracks in doc['animations'][name]['bones'].values()for track in tracks.values()for k in track)
    times=[0,duration/2,duration];result=deepcopy(doc);rows=[]
    for slot in case['failed_slots']:
        mesh=doc['skins'][0]['attachments'][slot][slot];owners=entries(mesh)
        triangles=[mesh['triangles'][i:i+3]for i in range(0,len(mesh['triangles']),3)]
        # Require a common bind point per vertex before blending relative frames.
        cursor=0
        for point in setup[slot]:
            count=mesh['vertices'][cursor];cursor+=1
            for _ in range(count):
                index,x,y,w=mesh['vertices'][cursor:cursor+4];cursor+=4
                a,b,c,d,tx,ty=rest[doc['bones'][index]['name']]
                if w>0 and math.dist(point,[a*x+b*y+tx,c*x+d*y+ty])>1e-4:
                    raise ValueError('polar_probe_inconsistent_bind_points')
        keys=[]
        for time in times:
            transforms=matrices(raw,name,time);origin=sample(raw,name,time)[0][slot]
            actual=sample(doc,name,time)[0][slot]
            corrected,evidence=solve(setup[slot],owners,doc['bones'],rest,transforms,shared_joint=shared_joint)
            rows.append(dict(slot=slot,time=time,raw=metrics(setup[slot],origin,triangles),
                actual=metrics(setup[slot],actual,triangles),polar=metrics(setup[slot],corrected,triangles),
                maximum_displacement_px=max(math.dist(a,b)for a,b in zip(origin,corrected)),
                single_bone_shift_px=max([math.dist(a,b)for a,b,row in zip(origin,corrected,owners)if sum(w>0 for _,w in row)==1]or[0]),
                solver=evidence))
            keys.append(dict(time=time,vertices=local_delta(doc,owners,transforms,origin,corrected)))
        result['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{})[slot]={'deform':keys}
    output.mkdir(parents=True,exist_ok=False)
    report=dict(parent=parent,character=case['character'],source_motion_unchanged=True,records=rows,shared_joint=shared_joint,
        authority='none',selected=False,scope='three_pose_comparison_not_full_clip_or_visual_acceptance')
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    candidate=stage(result,files,times,output/'candidate',parent)
    report['candidate']=candidate
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return summarize(report)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('cohort',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--shared-joint',action='store_true')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();cohort=json.loads(args.cohort.read_bytes());args.output.mkdir(parents=True,exist_ok=args.resume)
    rows=[]
    for case in cohort['rows']:
        folder=args.output/case['character'];receipt=folder/'probe.json'
        if args.resume and receipt.exists():
            report=json.loads(receipt.read_bytes())
            runtime=json.loads((folder/'candidate/runtime/report.json').read_bytes())
            if report['parent']!=case['artifact'] or report['shared_joint']!=args.shared_joint or runtime['bundle_sha256']!=report['candidate'] or runtime['passed']is not True:
                raise ValueError('polar_probe_resume_identity')
            AnimatedStore(folder/'candidate/isolated-store').read(report['candidate'])
            rows.append(summarize(report));continue
        try:
            rows.append(run(case,folder,shared_joint=args.shared_joint))
        except ValueError as exc:
            if str(exc)!='polar_skinning_unrelated_bones':raise
            failure=dict(character=case['character'],parent=case['artifact'],status='unsupported',reason=str(exc),selected=False)
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'failure.json').write_text(json.dumps(failure),encoding='utf-8');rows.append(failure)
        print(case['character']+' complete',flush=True)
    (args.output/'summary.json').write_text(json.dumps(dict(motion_identity=cohort['motion_identity'],rows=rows,selected=False),indent=2),encoding='utf-8')
