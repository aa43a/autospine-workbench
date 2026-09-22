"""Independent checks of baked region contacts at all requested sample times."""
import math
import numpy as np
from .affine_pose import sample,matrices
from .shoulder_contact_regions import constraints
from ...asset.planning.component_local_solver import metrics


def inspect(original,document,prepared,times,progress=lambda value:None):
    name='external-motion';rest=matrices(dict(original,animations={'setup':{}}),'setup',0)['chest']
    selected={r['slot'] for r,p in prepared};failures=[];max_region=0.;max_fixed=0.;max_pin=0.;max_move=0.;other=0.;speed=0.;previous=None;near_times=0
    for i,time in enumerate(times):
        if i%64==0:progress(dict(stage='validation',completed=i,total=len(times)))
        old=sample(original,name,time)[0];new=sample(document,name,time)[0];chest=matrices(original,name,time)['chest']
        other=max(other,max((math.dist(a,b) for s in old if s not in selected for a,b in zip(old[s],new[s],strict=True)),default=0.))
        for row,p in prepared:
            slot=row['slot'];fixed,regions=constraints(row,p,rest,chest,old[slot]);quality=metrics(row['points'],new[slot],row['triangles'])
            ratio=max((float(np.linalg.norm(np.asarray(r['inverse'])@(np.array(new[slot][r['vertex']])-r['center']))/r['radius']) for r in regions),default=0.)
            locked=max((math.dist(new[slot][v],fixed[v]) for v in range(len(fixed)) if v not in p['free'] and v not in p['locked']),default=0.)
            pin=max((math.dist(new[slot][v],fixed[v]) for v in p['locked']),default=0.)
            move=max(math.dist(a,b) for a,b in zip(old[slot],new[slot],strict=True))/p['context']['budget_px']
            if quality['bad_triangles'] or quality['max_edge_stretch']>2 or ratio>1+1e-7 or locked>1e-7 or pin>.5 or move>1+1e-7:
                failures.append(dict(slot=slot,time=time,geometry=quality,region_ratio=ratio,distal_error_px=locked,locked_pin_error_px=pin,displacement_ratio=move))
            max_region=max(max_region,ratio);max_fixed=max(max_fixed,locked);max_pin=max(max_pin,pin);max_move=max(max_move,move)
            if previous and time-previous[0]>=1e-6:
                speed=max(speed,max(math.dist(a,b) for a,b in zip(new[slot],previous[1][slot],strict=True))/(time-previous[0]))
        if previous and time-previous[0]<1e-6:near_times+=1
        else:previous=(time,new)
    return dict(passed=not failures and other<=1e-7,frames=len(times),failures=failures,max_region_ratio=max_region,
        max_distal_error_px=max_fixed,max_locked_pin_error_px=max_pin,locked_pin_limit_px=.5,max_displacement_ratio=max_move,unselected_error_px=other,
        maximum_vertex_speed_px_s=speed,speed_is_measurement_not_acceptance=True,
        speed_minimum_delta_seconds=1e-6,near_time_samples_excluded_from_speed_only=near_times)
