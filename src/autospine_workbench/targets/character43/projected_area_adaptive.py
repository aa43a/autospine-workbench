"""Refine failing interpolation times, always solving from the original motion."""
from .affine_area_repair import repair
from .projected_area_sampling import inspect


def build(document,name,setup_vertices,*,samples=129,rounds=3,temporal=False,terminal_collar=False,progress=None,proximal_ring=False,preserve_area=False,repair_band=False):
    if type(rounds) is not int or not 1 <= rounds <= 5:
        raise ValueError('projected_area_refinement_rounds')
    extra=set();history=[]
    for iteration in range(rounds):
        if progress:progress(dict(stage='refinement_round',iteration=iteration,max_rounds=rounds))
        result,evidence=repair(document,name,samples=samples,convergent=True,
            setup_vertices=setup_vertices,projected_reference=True,extra_times=sorted(extra),temporal=temporal,
            **({'terminal_collar':True} if terminal_collar else {}),
            **({'proximal_ring':True} if proximal_ring else {}),
            **({'preserve_area':True} if preserve_area else {}),
            **({'repair_band':True} if repair_band else {}),
            **({'progress':progress} if progress else {}))
        if progress:progress(dict(stage='check_interpolation',iteration=iteration))
        checked=inspect(result,name,[r['slot'] for r in evidence['records']],
            **({'preservation_source':document} if preserve_area else {}),
            **({'repair_support':{r['slot']:[v for c in r.get('terminal_collars',[]) for v in c['vertices']] for r in evidence['records']}} if repair_band else {}))
        history.append(dict(iteration=iteration,extra_times=sorted(extra),check=checked))
        new={r['time'] for r in checked['failures'] if not r['at_key']}-extra
        if not new or len(extra|new)>1025:
            break
        extra.update(new)
    evidence.update(profile='adaptive-transported-projected-area-budget10-v1' if temporal else 'adaptive-projected-area-budget10-v1',refinement=history,
                    validation='sampled_proxy_only_original_geometry_gate_retained')
    if terminal_collar:evidence['profile']='adaptive-terminal-collar-projected-area-budget10-v1'
    if proximal_ring:evidence['profile']='adaptive-proximal-ring-projected-area-budget10-v1-experiment'
    if preserve_area:evidence['profile']='adaptive-healthy-area-preservation-budget10-v1-experiment'
    if repair_band:evidence['profile']='adaptive-repair-band-preservation-budget10-v1-experiment'
    return result,evidence
