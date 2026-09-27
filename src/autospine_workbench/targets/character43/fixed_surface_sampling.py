"""Refine exact compensation keys against fixed-surface area, with hard limits."""
from bisect import bisect_right
from copy import deepcopy
import math
from .affine_pose import matrices, sample
from .deform_addition import entries
from .joint_repair_domain import expand
from .limb_transverse_repair import build as compensate
from .parent_setup_preservation import floors
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def build(parent,name,slot,required_times,*,rounds=6,maximum_keys=2049,progress=None):
    if type(rounds) is not int or not 1<=rounds<=8:raise ValueError('fixed_surface_rounds')
    mesh=parent['skins'][0]['attachments'][slot][slot];bones=parent['bones'];weights=entries(mesh)
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    free,domain=expand(weights,bones,triangles,1)
    fixed=[i for i,t in enumerate(triangles) if not any(free[v] for v in t)]
    def selected(doc):
        return dict(doc,skins=[dict(doc['skins'][0],attachments={slot:doc['skins'][0]['attachments'][slot]})])
    original=selected(parent);rest=deepcopy(original);rest['animations']={name:{'bones':{}}}
    setup=sample(rest,name,0)[0][slot];bind=matrices(rest,name,0)
    areas=[area(setup,t) for t in triangles];cache={}
    checked=set(required_times);extra=set();history=[];result=None;status='round_limit'
    for iteration in range(rounds):
        try:
            trial,evidence=compensate(parent,name,[slot],correction_frame='transverse',anchor_terminal=True,
                required_times=sorted(extra),maximum_keys=maximum_keys)
        except ValueError as error:
            if result is None or str(error) not in ('limb_transverse_key_limit','limb_transverse_interpolation_unresolved'):raise
            status=str(error);break
        result=trial;view=selected(result)
        times=[k['time'] for k in result['animations'][name]['attachments']['default'][slot][slot]['deform']]
        if any(not math.isfinite(t) or not times[0]<=t<=times[-1] for t in checked):
            raise ValueError('fixed_surface_times')
        checked.update(times)
        checked.update(a+(b-a)*i/8 for a,b in zip(times,times[1:]) for i in range(1,8))
        failures=[];worst={}
        for time in sorted(checked):
            if time not in cache:
                previous=sample(original,name,time)[0][slot]
                refs=reference(areas,triangles,weights,bones,bind,matrices(parent,name,time))
                limits,_=floors(previous,triangles,refs,areas);cache[time]=(refs,limits)
            refs,limits=cache[time];points=sample(view,name,time)[0][slot]
            ratios={i:area(points,triangles[i])/refs[i] for i in fixed}
            bad=[(i,limits[i]-ratios[i]) for i in fixed if ratios[i]<max(.5,limits[i]-1e-7)]
            if not bad:continue
            at_key=time in times;peak=max(d for _,d in bad)
            failures.append(dict(time=time,at_key=at_key,triangles=[i for i,_ in bad],maximum_deficit=peak))
            interval=bisect_right(times,time)-1
            if not at_key and (interval not in worst or peak>worst[interval][0]):worst[interval]=(peak,time)
        row=dict(iteration=iteration,keys=len(times),samples=len(checked),failures=failures)
        history.append(row)
        if progress:progress(dict(iteration=iteration,keys=len(times),samples=len(checked),failures=len(failures)))
        if not failures:status='sampled_fixed_floors_passed';break
        if any(r['at_key'] for r in failures):status='exact_key_failure';break
        proposed=set(times)|{r[1] for r in worst.values()}
        if len(proposed)>maximum_keys:status='key_limit';break
        extra=proposed
    return result,dict(profile='fixed-surface-adaptive-sampling-v1-experiment',status=status,
        history=history,times=sorted(checked),domain=domain,maximum_keys=maximum_keys,
        authority='none',selected=False,production_authorized=False,
        scope='fixed_area_floor_samples_only_not_mixed_area_contact_runtime_or_visual_acceptance')
