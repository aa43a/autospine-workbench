"""Joint sampled-interval corrective experiment, preserving both boundary poses."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_contact_regions import prepare_regions,constraints
from autospine_workbench.targets.character43.shoulder_region_validation import inspect
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.torso_projection_candidate import multiply
from autospine_workbench.targets.character43.deform_addition import entries,local_delta,value,runtime_union_times
from autospine_workbench.targets.character43.runtime_storage_reference import f32
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_material_shoulder_sequence import load


def solve_interval(original,doc,row,p,owner,t0,t1,bad):
    name='external-motion';slot=row['slot'];mid=f32((t0+t1)/2)
    free=sorted({v for i in bad for v in row['triangles'][i]}&set(p['free']))
    if not free or len(free)>32:raise ValueError('interval_repair_free_bound')
    tri=np.asarray(row['triangles']);rest=np.asarray(row['points'])
    edges=np.asarray(sorted({tuple(sorted((a,b))) for t in row['triangles'] for a,b in zip(t,t[1:]+t[:1])}))
    def areas(points):
        a=points[tri[:,1]]-points[tri[:,0]];b=points[tri[:,2]]-points[tri[:,0]]
        return .5*(a[:,0]*b[:,1]-a[:,1]*b[:,0])
    refs=areas(rest);lengths=np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1)
    influences=entries(doc['skins'][0]['attachments'][slot][slot]);atmid=matrices(doc,name,mid)
    setup=sample(dict(original,animations={'setup':{}}),'setup',0)[0]
    chest=matrices(dict(original,animations={'setup':{}}),'setup',0)['chest'];frames=[]
    times=sorted({t0+(t1-t0)*i/32 for i in range(33)}|{mid})
    for time in times:
        current=sample(doc,name,time)[0];source=sample(original,name,time)[0]
        transforms=matrices(doc,name,time);material,_=fit(setup[owner],source[owner])
        _,regions=constraints(row,p,chest,multiply(material,chest),source[slot])
        hat=(time-t0)/(mid-t0) if time<=mid else (t1-time)/(t1-mid);basis=[]
        for vertex in free:
            mat=np.zeros((2,2))
            for index,weight in influences[vertex]:
                bone=doc['bones'][index]['name'];a=transforms[bone];b=atmid[bone]
                mat+=weight*np.asarray([[a[0],a[1]],[a[2],a[3]]])@np.linalg.inv([[b[0],b[1]],[b[2],b[3]]])
            basis.append(hat*mat)
        frames.append((np.asarray(current[slot]),np.asarray(source[slot]),np.asarray(basis),regions))
    def checks(x):
        delta=x.reshape(-1,2);checks=[]
        for base,source,basis,regions in frames:
            points=base.copy();points[free]+=np.einsum('vij,vj->vi',basis,delta)
            ratios=areas(points)/refs;stretch=np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)/lengths
            checks.extend((ratios-.5001,1.9999-ratios,2-stretch,
                1-np.linalg.norm(points-source,axis=1)/p['context']['budget_px']))
            checks.append(np.asarray([1-np.linalg.norm(np.asarray(r['inverse'])@(points[r['vertex']]-r['center']))/r['radius'] for r in regions]))
        return np.concatenate(checks)
    result=minimize(lambda x:float(x@x),np.zeros(2*len(free)),jac=lambda x:2*x,
        method='SLSQP',constraints=[{'type':'ineq','fun':checks}],options={'maxiter':200,'ftol':1e-10})
    valid=np.isfinite(result.x).all() and float(checks(result.x).min())>=-1e-8
    evidence=dict(slot=slot,start=t0,end=t1,mid=mid,free=free,sample_times=times,
        optimizer_success=bool(result.success),message=str(result.message),
        min_constraint=float(checks(result.x).min()),feasible=bool(valid),
        max_increment_px=float(np.linalg.norm(result.x.reshape(-1,2),axis=1).max()))
    base=sample(doc,name,mid)[0][slot];changed=deepcopy(base)
    if valid:
        for v,d in zip(free,result.x.reshape(-1,2)):changed[v]=(np.asarray(base[v])+d).tolist()
    offsets=local_delta(doc,influences,atmid,base,changed);zero=[0.]*len(offsets)
    return [dict(time=t0,vertices=zero),dict(time=mid,vertices=offsets),dict(time=t1,vertices=zero)],evidence


def run(source,experiment,output):
    if output.exists():raise ValueError('interval_repair_output_exists')
    receipt,files=load(source);original,rows=contexts(files)
    report=json.loads((experiment/'report.json').read_bytes());raw=(experiment/'skeleton.json').read_bytes()
    if report['source_candidate']!=receipt['candidate_bundle_sha256'] or sha256(raw).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('interval_repair_identity')
    probe=json.loads((experiment/'intervals.json').read_bytes())
    if probe['skeleton_sha256']!=report['skeleton_sha256']:raise ValueError('interval_repair_probe_identity')
    doc=json.loads(raw);prepared=[(row,prepare_regions(row)) for row in rows];mapping={r['slot']:(r,p) for r,p in prepared}
    targets={}
    for r in probe['records']:targets.setdefault((r['slot'],r['start'],r['end']),set()).add(r['triangle'])
    if not 0<len(targets)<=8:raise ValueError('interval_repair_target_bound')
    output.mkdir();results=[];newtimes=set(report['validation_times'])
    for (slot,t0,t1),bad in sorted(targets.items()):
        row,p=mapping[slot];keys,evidence=solve_interval(original,doc,row,p,report['material_owners'][slot],t0,t1,bad)
        results.append(evidence);print(json.dumps(evidence),flush=True)
        if not evidence['feasible']:continue
        timeline=doc['animations']['external-motion']['attachments']['default'][slot][slot]
        old=timeline['deform'];size=len(keys[0]['vertices'])
        timeline['deform']=[dict(time=t,vertices=[a+b for a,b in zip(value(old,t,size),value(keys,t,size))])
                           for t in runtime_union_times(old,keys)]
        newtimes.update(evidence['sample_times'])
    raw=canonical_bytes(doc);(output/'skeleton.json').write_bytes(raw)
    result=dict(source_candidate=report['source_candidate'],skeleton_sha256=sha256(raw).hexdigest(),
        parent_skeleton_sha256=report['skeleton_sha256'],rows=report['rows'],intervals=results,selected=False,authority='none',
        scope='sampled_interval_constraints_requires_dense_validation_and_runtime')
    (output/'report.json').write_bytes(canonical_bytes(result))
    result['validation']=inspect(original,doc,prepared,sorted(newtimes))
    result['validation_times']=sorted(newtimes);(output/'report.json').write_bytes(canonical_bytes(result))
    print(json.dumps({'passed':result['validation']['passed'],'frames':len(newtimes),
                      'failures':len(result['validation']['failures'])}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','experiment','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.output)
