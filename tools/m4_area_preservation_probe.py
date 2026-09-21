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


def run(folder, attribution, output, *, expanded=False, repair_band=False):
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
            floors,band=outside_repair_band(base,triangles,refs)
        context=dict(row={'triangles':triangles},areas=refs,edges=edges,
            lengths=[math.dist(setup[slot][a],setup[slot][b]) for a,b in edges],
            free=free,budget=row['budget_px'],minimum_ratios=floors)
        points,solver=project(context,base,initial=initial)
        if not solver['converged']:
            points,solver['local']=refine(context,base,points,analytic=True,**({'expanded':True} if expanded else {}))
        ratios=[area(points,t)/a for t,a in zip(triangles,refs)]
        failed=[i for i,(r,f) in enumerate(zip(ratios,floors)) if r<f-1e-7 or r>2]
        displacement=max(math.dist(a,b) for a,b in zip(base,points))
        fixed=max((math.dist(a,b) for a,b,f in zip(base,points,free) if not f),default=0)
        stretch=max(math.dist(points[a],points[b])/length for (a,b),length in zip(edges,context['lengths']))
        index=target['triangle']
        result=dict(slot=slot,time=time,triangle=index,solver=solver,
            preservation_scope='outside_one_ring_repair_band' if repair_band else 'all_triangles',repair_band=band,
            failed_triangles=failed,maximum_displacement=displacement,budget_px=context['budget'],
            maximum_fixed_displacement=fixed,max_edge_stretch=stretch,
            previous_setup_ratio=area(initial,triangles[index])/setup_areas[index],
            proposed_setup_ratio=area(points,triangles[index])/setup_areas[index],
            target_projected_floor=floors[index],proposed_projected_ratio=ratios[index],
            passed=not failed and displacement<=context['budget']+1e-7 and fixed<=1e-7 and stretch<=2+1e-7)
        rows.append(result);print(json.dumps(result),flush=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(dict(profile='healthy-area-preservation-probe-v1',candidate=identity,authority='none',
            selected=False,scope='attributed_poses_only_not_animation_or_visual_acceptance',rows=rows),f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('folder','attribution','output'):parser.add_argument(key,type=Path)
    parser.add_argument('--expanded',action='store_true')
    parser.add_argument('--repair-band',action='store_true')
    args=parser.parse_args();run(args.folder,args.attribution,args.output,expanded=args.expanded,repair_band=args.repair_band)
