"""Blender source rotations driving a target front-surface hypothesis."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.limb_surface_proxy import rotation
from autospine_workbench.targets.character43.surface_chain_skin import deform
from autospine_workbench.targets.character43.surface_projection_evidence import inspect


def orthogonal(matrix):
    value=np.asarray(matrix,float); u,scales,v=np.linalg.svd(value)
    if np.linalg.det(value)<=0 or np.max(abs(scales-1))>1e-5:
        raise ValueError('source_rotation_not_rigid')
    return u@v,float(np.max(abs(value-u@v)))


def run(surface_path,scene_path,reference_path,output):
    raw=surface_path.read_bytes(); surface=json.loads(raw); scene_raw=scene_path.read_bytes()
    if hashlib.sha256(scene_raw).hexdigest()!=surface['source_sha256']:raise ValueError('target_source_changed')
    doc=json.loads(scene_raw)['skeleton']; ref=json.loads(reference_path.read_bytes())
    motion=next(Path(p) for p,h in ref['sources'].items() if h==ref['motion_sha256'])
    if hashlib.sha256(motion.read_bytes()).hexdigest()!=ref['motion_sha256']:raise ValueError('motion_changed')
    spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('render-motion-surface-reference.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    times=sorted({0.,.9,*[r['time'] for r in ref['captures']]})
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
            posed,posed_heads=deform(s['vertices'],influences,heads,turns,heads[0])
            evidence=inspect(s['vertices'],posed,s['triangles'],np.eye(3))
            rows.append(dict(slot=slot,time=sample['time'],vertices=posed.tolist(),
                             heads=posed_heads.tolist(),evidence=evidence))
    output.mkdir(parents=True,exist_ok=False)
    result=dict(surface_sha256=hashlib.sha256(raw).hexdigest(),motion_sha256=ref['motion_sha256'],
                clock=clock,camera_basis=basis.tolist(),records=rows,accepted=False,
                maximum_rotation_orthogonalization_delta=max(rotation_errors),
                limitations=['rest_axis_calibration_is_hypothesis','hip_fixed_no_contact_constraint',
                             'linear_skinning_not_corrective','no_visibility_or_material_render_yet'])
    (output/'poses.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    summary=[dict(slot=r['slot'],time=r['time'],
                  intrinsic_failed=sum(not t.get('intrinsic_gate_passed',False) for t in r['evidence']['triangles']),
                  projection_only=sum(t.get('projected_area_failure_with_intrinsic_pass',False) for t in r['evidence']['triangles'])) for r in rows]
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('surface','scene','reference','output'):p.add_argument(key,type=Path)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(a.surface,a.scene,a.reference,a.output)
