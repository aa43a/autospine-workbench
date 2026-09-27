"""Bake bounded joint-neighbourhood corrections and inspect actual interpolation."""
from copy import deepcopy
import math
from .affine_pose import matrices, sample
from .deform_addition import entries, local_delta, value
from .joint_repair_domain import expand
from .parent_pose_area_repair import solve, verify_source
from .parent_setup_preservation import floors
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def build(parent, candidate, name, slot, required_times, *, progress=None):
    verify_source(parent,candidate,name,slot)
    original=candidate['animations'][name]['attachments']['default'][slot][slot]['deform']
    times=[k['time'] for k in original]
    if len(times)>2049 or not times or any(a>=b for a,b in zip(times,times[1:])):
        raise ValueError('boundary_animation_key_inventory')
    if any(not math.isfinite(t) or not times[0]<=t<=times[-1] for t in required_times):
        raise ValueError('boundary_animation_validation_times')
    rest=deepcopy(parent);rest['animations']={name:{'bones':{}}}
    setup=sample(rest,name,0)[0][slot];bind=matrices(rest,name,0)
    mesh=parent['skins'][0]['attachments'][slot][slot];bones=parent['bones']
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    areas=[area(setup,t) for t in triangles];influences=entries(mesh)
    free,domain=expand(influences,bones,triangles,1)
    used={bones[b]['name'] for row in influences for b,w in row if w>0}
    chain=[math.hypot(b['x'],b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
    if not chain or min(chain)<=0:raise ValueError('boundary_animation_chain')
    edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
    lengths=[math.dist(setup[a],setup[b]) for a,b in edges]
    base=dict(row={'triangles':triangles},free=free,budget=.1*min(chain),edges=edges,lengths=lengths)
    def pose(time):
        transforms=matrices(parent,name,time)
        previous=sample(parent,name,time)[0][slot]
        origin=sample(candidate,name,time)[0][slot]
        refs=reference(areas,triangles,influences,bones,bind,transforms)
        return transforms,previous,origin,dict(base,areas=refs)
    result=deepcopy(candidate);keys=[];solvers=[]
    for index,time in enumerate(times):
        transforms,previous,origin,context=pose(time)
        corrected,evidence=solve(context,origin,previous,areas,protect_setup=True,local_refinement=True)
        delta=local_delta(parent,influences,transforms,origin,corrected)
        prior=value(original,time,len(delta))
        keys.append(dict(time=time,vertices=[a+b for a,b in zip(prior,delta,strict=True)]))
        solvers.append(dict(time=time,converged=evidence['converged']))
        if progress and index%32==0:progress(dict(stage='bake',index=index,total=len(times)))
    result['animations'][name]['attachments']['default'][slot][slot]['deform']=keys
    verify_source(parent,result,name,slot)
    checked=sorted(set(required_times)|set(times)|{a+(b-a)*u for a,b in zip(times,times[1:]) for u in (.25,.5,.75)})
    failures=[];peak_shift=0.;peak_edge=0.;peak_fixed=0.;min_setup=math.inf;max_delta_step=0.;last=None
    for index,time in enumerate(checked):
        _,previous,origin,context=pose(time);points=sample(result,name,time)[0][slot]
        limits,_=floors(previous,triangles,context['areas'],areas)
        ratios=[area(points,t)/r for t,r in zip(triangles,context['areas'])]
        setup_ratios=[area(points,t)/r for t,r in zip(triangles,areas)]
        parent_ratios=[area(previous,t)/r for t,r in zip(triangles,areas)]
        failed=[i for i,(r,f) in enumerate(zip(ratios,limits)) if r<max(.5,f-1e-7) or r>2]
        healthy=[i for i,(r,p) in enumerate(zip(setup_ratios,parent_ratios)) if .5<=p<=2 and not .5<=r<=2]
        regressed=[i for i,(r,p) in enumerate(zip(setup_ratios,parent_ratios)) if 0<p<.5 and r<p-1e-7]
        shifts=[math.dist(a,b) for a,b in zip(origin,points)]
        shift=max(shifts);fixed=max([s for s,f in zip(shifts,free) if not f] or [0.])
        edge=max(math.dist(points[a],points[b])/length for (a,b),length in zip(edges,lengths))
        if failed or healthy or regressed or shift>base['budget']+1e-7 or fixed>1e-7 or edge>2:
            failures.append(dict(time=time,at_key=time in times,triangles=failed,healthy=healthy,
                regressed=regressed,shift_px=shift,fixed_shift_px=fixed,max_edge_ratio=edge))
        peak_shift=max(peak_shift,shift);peak_fixed=max(peak_fixed,fixed);peak_edge=max(peak_edge,edge)
        min_setup=min(min_setup,min(setup_ratios))
        delta=[[p[k]-o[k] for k in (0,1)] for p,o in zip(points,origin)]
        if last is not None:max_delta_step=max(max_delta_step,max(math.dist(a,b) for a,b in zip(last,delta)))
        last=delta
        if progress and index%128==0:progress(dict(stage='interpolation',index=index,total=len(checked)))
    return result,dict(profile='joint-boundary-animation-v1-experiment',domain=domain,
        key_count=len(keys),solver_failures=[r for r in solvers if not r['converged']],
        times=checked,failures=failures,maximum_shift_px=peak_shift,maximum_fixed_shift_px=peak_fixed,
        maximum_edge_ratio=peak_edge,minimum_setup_area_ratio=min_setup,
        maximum_sampled_correction_step_px=max_delta_step,budget_px=base['budget'],
        local_constraints_passed=not failures and all(r['converged'] for r in solvers),
        authority='none',selected=False,production_authorized=False,
        scope='sampled_baked_local_constraints_not_setup_geometry_contact_runtime_or_visual_acceptance')
