"""Test a bounded hidden-limb correction with distal and visible material fixed."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.material_reachability import inspect
from autospine_workbench.targets.character43.material_alpha_batch import sample as alpha_sample
from autospine_workbench.targets.character43.regional_material_support import solve
from autospine_workbench.targets.character43.skirt_motion_contact import locate,transport
from autospine_workbench.asset.planning.component_local_solver import metrics


def run(runtime,experiment,grid_path,guards_path,output,time=.9):
    output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((runtime/'report.json').read_bytes())
    files=AnimatedStore(runtime/'isolated-store').read(receipt['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json']);diagnosis=json.loads((experiment/'report.json').read_bytes())
    grid=json.loads(grid_path.read_bytes());guards=json.loads(guards_path.read_bytes())
    if (sha256(files['skeleton.json']).hexdigest()!=diagnosis['skeleton_sha256'] or
        diagnosis['source_candidate']!=grid['candidate_bundle_sha256'] or
        any(grid[k]!=guards[k] for k in ('candidate_bundle_sha256','skeleton_sha256','limb','cloth'))):
        raise ValueError('limb_occlusion_identity')
    frame=next(f for f in diagnosis['frames'] if f['time']==time)
    limb,cloth=grid['limb'],grid['cloth'];attachments=doc['skins'][0]['attachments']
    lm,cm=attachments[limb][limb],attachments[cloth][cloth]
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    posed=sample(doc,'external-motion',time)[0]
    texture=Image.open(BytesIO(files['images/'+cm.get('path',cloth)+'.png'])).convert('RGBA')
    alpha=np.asarray(texture.getchannel('A'),float)
    fixed={i for i,row in enumerate(entries(lm)) if any(w>0 and doc['bones'][b]['name'].startswith('foot') for b,w in row)}
    distal=sorted(fixed)
    visible=[locate(setup[limb],lm['triangles'],r['source_material_world']) for r in guards['rows']
             if r['exposure_kind']=='previously_visible_limb_material']
    if not distal or not visible:raise ValueError('limb_occlusion_protection_missing')
    fixed.update(v for ids,_ in visible for v in ids)
    supports=[];targets=[];witnesses=[]
    for failure in frame['uncovered']:
        ids,weights=grid['grid'][failure['sample']]['anchor']
        point=transport(posed[limb],(ids,weights))
        witness=inspect(cm,posed[cloth],alpha,point,budget=2,threshold=128)
        witnesses.append(dict(sample=failure['sample'],**witness))
        if witness['status']=='material_witness_within_budget':
            supports.append(dict(vertices=ids,weights=weights));targets.append(witness['witness']['world'])
    result=dict(time=time,skeleton_sha256=diagnosis['skeleton_sha256'],limb=limb,cloth=cloth,
        witnesses=witnesses,distal_fixed_vertices=distal,visible_fixed_vertices=sorted(fixed-set(distal)),
        authority='none',selected=False,scope='single_pose_hidden_limb_test_not_animation_or_visual_acceptance',
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (grid_path,guards_path,experiment/'report.json')})
    if len(supports)!=len(frame['uncovered']) or not supports:
        result['status']='missing_bounded_cloth_support'
    else:
        tri=np.asarray(lm['triangles']).reshape(-1,3).tolist()
        corrected,movement=solve(setup[limb],posed[limb],tri,supports,targets,fixed,
            budget=2,exact=list(range(len(supports))),geometry=True)
        result.update(movement=movement,before_geometry=metrics(setup[limb],posed[limb],tri))
        if corrected is None:result['status']='joint_solver_rejected'
        else:
            qa=metrics(setup[limb],corrected,tri)
            queries=[transport(corrected,g['anchor']) for g in grid['grid']]
            values=alpha_sample(cm,posed[cloth],alpha,queries)
            failed=[i for i,(g,a) in enumerate(zip(grid['grid'],values)) if g['source_cloth_alpha']>=8 and g['limb_alpha']>=8 and a<8]
            # Moving a tracked material point can merely replace its old visible
            # pixel with a different point on the same limb. Test that separately.
            leg_alpha=np.asarray(Image.open(BytesIO(files['images/'+lm.get('path',limb)+'.png'])).convert('RGBA').getchannel('A'),float)
            old_queries=[transport(posed[limb],grid['grid'][r['sample']]['anchor']) for r in frame['uncovered']]
            old_limb=alpha_sample(lm,posed[limb],leg_alpha,old_queries)
            new_limb=alpha_sample(lm,corrected,leg_alpha,old_queries)
            cloth_alpha=alpha_sample(cm,posed[cloth],alpha,old_queries)
            stationary=[dict(sample=r['sample'],world=q,cloth_alpha=c,limb_before=a,limb_after=b,
                exposed_limb_remains=c<8 and b>=8) for r,q,c,a,b in zip(frame['uncovered'],old_queries,cloth_alpha,old_limb,new_limb)]
            fixed_error=max(np.linalg.norm(np.asarray(corrected)[sorted(fixed)]-np.asarray(posed[limb])[sorted(fixed)],axis=1))
            result.update(after_geometry=qa,coverage_failed=failed,coverage_alpha=values,fixed_error_px=float(fixed_error),
                original_location_checks=stationary,visual_repair_proven=False,
                status='sampled_pose_passed' if not qa['bad_triangles'] and qa['max_edge_stretch']<=2 and not failed and fixed_error<=1e-7 else 'sampled_pose_failed')
            result['material_pose_passed']=result['status']=='sampled_pose_passed'
            if any(r['exposed_limb_remains'] for r in stationary):result['status']='original_exposure_remains'
            (output/'posed-limb.json').write_bytes(canonical_bytes({str(time):corrected}))
    (output/'report.json').write_bytes(canonical_bytes(result))
    print(json.dumps({k:result[k] for k in ('time','status','material_pose_passed','original_location_checks') if k in result}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','experiment','grid_path','guards_path','output'):p.add_argument(n,type=Path)
    p.add_argument('--time',type=float,default=.9)
    a=p.parse_args();run(a.runtime,a.experiment,a.grid_path,a.guards_path,a.output,a.time)
