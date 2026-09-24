"""Blender source rotations driving a target front-surface hypothesis."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from mathutils import Matrix

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.limb_surface_proxy import rotation
from autospine_workbench.targets.character43.surface_chain_skin import deform
from autospine_workbench.targets.character43.surface_projection_evidence import inspect
from autospine_workbench.targets.character43.dual_quaternion_skin import deform as dq_deform
from autospine_workbench.targets.character43.surface_swing_control import decompose


def orthogonal(matrix):
    value=np.asarray(matrix,float); u,scales,v=np.linalg.svd(value)
    if np.linalg.det(value)<=0 or np.max(abs(scales-1))>1e-5:
        raise ValueError('source_rotation_not_rigid')
    return u@v,float(np.max(abs(value-u@v)))


def run(surface_path,scene_path,reference_path,output,full=False,swing_control=False):
    raw=surface_path.read_bytes(); surface=json.loads(raw); scene_raw=scene_path.read_bytes()
    if hashlib.sha256(scene_raw).hexdigest()!=surface['source_sha256']:raise ValueError('target_source_changed')
    doc=json.loads(scene_raw)['skeleton']; ref=json.loads(reference_path.read_bytes())
    motion=next(Path(p) for p,h in ref['sources'].items() if h==ref['motion_sha256'])
    if hashlib.sha256(motion.read_bytes()).hexdigest()!=ref['motion_sha256']:raise ValueError('motion_changed')
    spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('render-motion-surface-reference.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    times=sorted({0.,.9,*[r['time'] for r in ref['captures']]})
    if full:
        first,last=ref['clock']['frame_range'];fps=ref['clock']['fps']
        times=[i/(2*fps) for i in range(int(round((last-first)*2))+1)]
    rest,samples,world,clock=helper.capture_source(motion,times)
    camera=np.array(ref['captures'][0]['camera_world_matrix'])[:3,:3].T
    # Camera right/up/toward-viewer is a proper orthonormal frame.
    basis,error=orthogonal(camera@np.array(world.to_quaternion().to_matrix()))
    rotation_errors=[error]
    target=matrices(dict(doc,animations={'setup':{}}),'setup',0)
    rows=[]
    for slot,s in surface['surfaces'].items():
        side='r' if slot=='layer-003' else 'l'; prefix='Right' if side=='r' else 'Left'
        names=[f'{n}_{side}' for n in ('thigh','calf','foot')]
        source_names=[prefix+n for n in ('UpLeg','Leg','Foot')]
        heads=np.array([[*target[n][4:],0.] for n in names])
        corrections=[]; rest_rotations=[]
        for name,source_name in zip(names,source_names):
            source_rest,error=orthogonal(basis@np.array(rest[source_name].to_quaternion().to_matrix()))
            rotation_errors.append(error)
            a,b,c,d,x,y=target[name]
            corrections.append(rotation(source_rest[:,1],[a,c,0]))
            rest_rotations.append(source_rest)
        influences=[[(names.index(s['source_bones'][i]['name']),w) for i,w in row if w>0]
                    for row in entries({'vertices':s['source_weighted_vertices']})]
        for sample in samples:
            turns=[]
            for name,c,r in zip(source_names,corrections,rest_rotations):
                pose,error=orthogonal(basis@np.array(sample['bones'][name]['matrix'].to_quaternion().to_matrix()))
                rotation_errors.append(error)
                turns.append(c@pose@r.T@c.T)
            # Fix hip for this isolated test; no floor-contact claim.
            twist_records=[];head_difference=0.
            if swing_control:
                _,source_heads=deform(s['vertices'],influences,heads,turns,heads[0])
                controlled=[]
                for n,r in zip(names,turns):
                    a,b,c,d,x,y=target[n];swing,record=decompose(r,[a,c,0])
                    record['bone']=n;twist_records.append(record);controlled.append(swing)
                turns=controlled
            posed,posed_heads=deform(s['vertices'],influences,heads,turns,heads[0])
            if swing_control:
                head_difference=float(np.max(np.linalg.norm(posed_heads-source_heads,axis=1)))
                if head_difference>1e-6:raise ValueError('swing_control_changed_chain_endpoints')
            evidence=inspect(s['vertices'],posed,s['triangles'],np.eye(3))
            translations=[p-r@h for p,r,h in zip(posed_heads,turns,heads)]
            dq=dq_deform(s['vertices'],influences,
                         [list(Matrix(r.tolist()).to_quaternion()) for r in turns],translations)
            dq_evidence=inspect(s['vertices'],dq,s['triangles'],np.eye(3))
            failed=[t['triangle'] for t in evidence['triangles'] if not t.get('intrinsic_gate_passed',False)]
            mixed=sum(any(len(influences[i])>1 for i in s['triangles'][tid]) for tid in failed)
            rows.append(dict(slot=slot,time=sample['time'],vertices=posed.tolist(),
                             heads=posed_heads.tolist(),evidence=evidence,
                             dq_vertices=dq.tolist(),dq_evidence=dq_evidence,
                             twist_control=twist_records,source_chain_head_difference=head_difference,
                             failed_triangles_with_mixed_vertex=mixed))
    output.mkdir(parents=True,exist_ok=False)
    result=dict(surface_sha256=hashlib.sha256(raw).hexdigest(),motion_sha256=ref['motion_sha256'],
                clock=clock,camera_basis=basis.tolist(),records=rows,accepted=False,
                sampling='source_keys_and_half_frames' if full else 'four_diagnostic_poses',
                rotation_mode='swing_control_source_twist_removed' if swing_control else 'source_full_rotation',
                maximum_rotation_orthogonalization_delta=max(rotation_errors),
                limitations=['rest_axis_calibration_is_hypothesis','hip_fixed_no_contact_constraint',
                             'linear_skinning_not_corrective','no_visibility_or_material_render_yet'])
    (output/'poses.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    summary=[dict(slot=r['slot'],time=r['time'],
                  intrinsic_failed=sum(not t.get('intrinsic_gate_passed',False) for t in r['evidence']['triangles']),
                  dq_intrinsic_failed=sum(not t.get('intrinsic_gate_passed',False) for t in r['dq_evidence']['triangles']),
                  mixed_failed=r['failed_triangles_with_mixed_vertex'],
                  source_chain_head_difference=r['source_chain_head_difference'],
                  projection_only=sum(t.get('projected_area_failure_with_intrinsic_pass',False) for t in r['evidence']['triangles'])) for r in rows]
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if full:
        print(json.dumps({slot:dict(samples=len([r for r in summary if r['slot']==slot]),
            lbs_failed_poses=sum(r['intrinsic_failed']>0 for r in summary if r['slot']==slot),
            dq_failed_poses=sum(r['dq_intrinsic_failed']>0 for r in summary if r['slot']==slot),
            dq_max_failed=max(r['dq_intrinsic_failed'] for r in summary if r['slot']==slot))
            for slot in surface['surfaces']}))
    else: print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('surface','scene','reference','output'):p.add_argument(key,type=Path)
    p.add_argument('--full',action='store_true')
    p.add_argument('--swing-control',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(a.surface,a.scene,a.reference,a.output,a.full,a.swing_control)
