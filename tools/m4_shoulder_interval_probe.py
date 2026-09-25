"""Compare interval area bounds with actual bone/deform sampling; never authorize."""
import argparse
from bisect import bisect_right
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.linear_triangle_interval import extrema,signed_area
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_material_shoulder_sequence import load
from m4_material_shoulder_feedback import solve_times


def run(source,experiment,output):
    if output.exists():raise ValueError('shoulder_interval_output_exists')
    receipt,files=load(source);report=json.loads((experiment/'report.json').read_bytes())
    raw=(experiment/'skeleton.json').read_bytes()
    if receipt['candidate_bundle_sha256']!=report['source_candidate'] or sha256(raw).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('shoulder_interval_identity')
    _,rows=contexts(files);rows={r['slot']:r for r in rows};doc=json.loads(raw)
    knots=solve_times(report);targets=set()
    for failure in report['validation']['failures']:
        interval=min(len(knots)-2,max(0,bisect_right(knots,failure['time'])-1))
        for triangle in failure['geometry']['bad_triangles']:
            targets.add((failure['slot'],interval,triangle))
    if len(targets)>128:raise ValueError('shoulder_interval_probe_bound')
    cache={}
    def world(time):
        if time not in cache:cache[time]=sample(doc,'external-motion',time)[0]
        return cache[time]
    results=[]
    for slot,index,triangle in sorted(targets):
        t0,t1=knots[index:index+2];row=rows[slot];vertices=row['triangles'][triangle]
        setup=[row['points'][i] for i in vertices]
        start=[world(t0)[slot][i] for i in vertices];end=[world(t1)[slot][i] for i in vertices]
        predicted=extrema(setup,start,end);ratios=[];error=0.
        us=sorted({i/16 for i in range(17)}|{predicted['minimum']['u'],predicted['maximum']['u']})
        for u in us:
            points=[world(t0+(t1-t0)*u)[slot][i] for i in vertices]
            linear=[[(1-u)*a+u*b for a,b in zip(p,q)] for p,q in zip(start,end)]
            error=max(error,max(math.dist(a,b) for a,b in zip(points,linear)))
            ratios.append(dict(time=t0+(t1-t0)*u,area_ratio=signed_area(points)/signed_area(setup)))
        results.append(dict(slot=slot,triangle=triangle,start=t0,end=t1,linear_prediction=predicted,
            actual_minimum=min(ratios,key=lambda x:x['area_ratio']),
            actual_maximum=max(ratios,key=lambda x:x['area_ratio']),
            max_world_linear_error_px=error,linear_world_model_rejected=error>1e-7))
    result=dict(source_candidate=report['source_candidate'],skeleton_sha256=report['skeleton_sha256'],
        authority='none',selected=False,scope='interval_model_diagnostic_not_continuous_certificate',
        records=results,actual_sample_times=sorted(cache))
    output.write_bytes(canonical_bytes(result))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','experiment','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.output)
