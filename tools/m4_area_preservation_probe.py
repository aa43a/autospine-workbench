"""Check healthy-area preservation on exact attributed poses, without publishing motion."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.area_preservation import from_pose
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder, attribution, output, *, expanded=False, repair_band=False, collar_band=False,recover_source=False,recover_area=False):
    if collar_band and not repair_band:raise ValueError('collar_band_requires_repair_band')
    if recover_area and not recover_source:raise ValueError('area_recovery_requires_source')
    receipt=json.loads((folder/'report.json').read_bytes());evidence=json.loads(attribution.read_bytes())
    identity=receipt['candidate_bundle_sha256']
    if evidence['candidate']!=identity:raise ValueError('preservation_candidate_mismatch')
    files=AnimatedStore(folder/'isolated-store').read(identity)
    doc=json.loads(files['skeleton.json']);name='external-motion'
    bare=deepcopy(doc);bare['animations'][name].pop('attachments',None)
    rest=deepcopy(bare);rest['animations'][name]={'bones':{}}
    setup=json.loads(files['rig-setup-reference.json'])['vertices']
    corrections=json.loads((folder/'correction.json').read_bytes())['records'];rows=[]
    for target in evidence['rows']:
        slot,time=target['slot'],target['time'];row=next(r for r in corrections if r['slot']==slot)
        mesh=doc['skins'][0]['attachments'][slot][slot];flat=mesh['triangles']
        triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        data=mesh['vertices'];i=0;owners=[]
        while i<len(data):
            n=data[i];i+=1;owners.append([(data[i+4*j],data[i+4*j+3]) for j in range(n)]);i+=4*n
        free=[sum(w>0 for _,w in entries)>1 for entries in owners]
        for collar in row.get('terminal_collars',[]):
            for v in collar['vertices']:free[v]=True
        edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
        setup_areas=[area(setup[slot],t) for t in triangles]
        refs=reference(setup_areas,triangles,owners,doc['bones'],matrices(rest,name,0),matrices(doc,name,time))
        base=sample(bare,name,time)[0][slot];initial=sample(doc,name,time)[0][slot]
        floors=from_pose(base,triangles,refs)
        band=[]
        if repair_band:
            from autospine_workbench.targets.character43.area_preservation import outside_repair_band
            support={v for c in row.get('terminal_collars',[]) for v in c['vertices']} if collar_band else ()
            floors,band=outside_repair_band(base,triangles,refs,support_vertices=support)
        context=dict(row={'triangles':triangles},areas=refs,edges=edges,
            lengths=[math.dist(setup[slot][a],setup[slot][b]) for a,b in edges],
            free=free,budget=row['budget_px'],minimum_ratios=floors)
        if recover_source:
            if 'fixed_repair_band' not in row:raise ValueError('source_recovery_requires_fixed_band')
            band=row['fixed_repair_band']
            for i in band:context['minimum_ratios'][i]=.5
            points,solver=refine(context,base,initial,analytic=True,expanded=True,recover_source=True,recover_area=recover_area)
        else:
            points,solver=project(context,base,initial=initial)
        if not recover_source and not solver['converged']:
            points,solver['local']=refine(context,base,points,analytic=True,**({'expanded':True} if expanded else {}))
        ratios=[area(points,t)/a for t,a in zip(triangles,refs)]
        failed=[i for i,(r,f) in enumerate(zip(ratios,floors)) if r<f-1e-7 or r>2]
        displacement=max(math.dist(a,b) for a,b in zip(base,points))
        fixed=max((math.dist(a,b) for a,b,f in zip(base,points,free) if not f),default=0)
        stretch=max(math.dist(points[a],points[b])/length for (a,b),length in zip(edges,context['lengths']))
        index=target['triangle']
        before_setup=[area(initial,t)/a for t,a in zip(triangles,setup_areas)]
        after_setup=[area(points,t)/a for t,a in zip(triangles,setup_areas)]
        result=dict(slot=slot,time=time,triangle=index,solver=solver,
            minimum_setup_ratio_before=min(before_setup),minimum_setup_ratio_after=min(after_setup),
            newly_failed_setup_triangles=[i for i,(a,b) in enumerate(zip(before_setup,after_setup)) if .5<=a<=2 and not .5<=b<=2],
            source_recovery=recover_source,points=points if recover_source else None,
            preservation_scope='outside_existing_fixed_band' if recover_source else 'outside_repair_and_collar_band' if collar_band else 'outside_one_ring_repair_band' if repair_band else 'all_triangles',repair_band=band,
            failed_triangles=failed,maximum_displacement=displacement,budget_px=context['budget'],
            maximum_fixed_displacement=fixed,max_edge_stretch=stretch,
            previous_setup_ratio=area(initial,triangles[index])/setup_areas[index],
            proposed_setup_ratio=area(points,triangles[index])/setup_areas[index],
            target_projected_floor=floors[index],proposed_projected_ratio=ratios[index],
            passed=not failed and displacement<=context['budget']+1e-7 and fixed<=1e-7 and stretch<=2+1e-7)
        result['passed_scope']='projected_constraints_only_not_original_setup_geometry'
        result['eligible_for_sequence_experiment']=bool(result['passed'] and not result['newly_failed_setup_triangles']
            and min(after_setup)>=min(before_setup) and result['proposed_setup_ratio']>result['previous_setup_ratio'])
        rows.append(result);print(json.dumps({k:v for k,v in result.items() if k!='points'}),flush=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(dict(profile='healthy-area-preservation-probe-v1',candidate=identity,authority='none',
            selected=False,scope='attributed_poses_only_not_animation_or_visual_acceptance',rows=rows),f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('folder','attribution','output'):parser.add_argument(key,type=Path)
    parser.add_argument('--expanded',action='store_true')
    parser.add_argument('--repair-band',action='store_true')
    parser.add_argument('--collar-band',action='store_true')
    parser.add_argument('--recover-source',action='store_true')
    parser.add_argument('--recover-area',action='store_true')
    args=parser.parse_args();run(args.folder,args.attribution,args.output,expanded=args.expanded,repair_band=args.repair_band,collar_band=args.collar_band,recover_source=args.recover_source,recover_area=args.recover_area)
