"""Measured endpoint solver headroom, never a relaxation of acceptance floors."""
from bisect import bisect_right
from copy import deepcopy
from hashlib import sha256
from ...automation.storage_io import canonical_bytes
from .affine_pose import matrices, sample
from .deform_addition import entries
from .interpolation_area_margin import LIMIT
from .joint_repair_domain import expand
from .parent_pose_area_repair import verify_source
from .parent_setup_preservation import floors
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def measure(parent, candidate, report, name, slot):
    if sha256(canonical_bytes(candidate)).hexdigest()!=report['skeleton_sha256'] or report['slot']!=slot:
        raise ValueError('boundary_margin_source_identity')
    verify_source(parent,candidate,name,slot)
    rest=deepcopy(parent);rest['animations']={name:{'bones':{}}}
    setup=sample(rest,name,0)[0][slot];bind=matrices(rest,name,0);bones=parent['bones']
    mesh=parent['skins'][0]['attachments'][slot][slot];weights=entries(mesh)
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    areas=[area(setup,t) for t in triangles];free,_=expand(weights,bones,triangles,1)
    times=[k['time'] for k in candidate['animations'][name]['attachments']['default'][slot][slot]['deform']]
    margins={};fixed=[];capped=0
    for row in report['failures']:
        if row['at_key']:continue
        time=row['time'];index=bisect_right(times,time)-1
        if not 0<=index<len(times)-1:raise ValueError('boundary_margin_interval')
        previous=sample(parent,name,time)[0][slot];points=sample(candidate,name,time)[0][slot]
        refs=reference(areas,triangles,weights,bones,bind,matrices(parent,name,time))
        limits,_=floors(previous,triangles,refs,areas)
        for i in row['triangles']:
            deficit=limits[i]-area(points,triangles[i])/refs[i]
            if deficit<=0:continue
            if not any(free[v] for v in triangles[i]):
                fixed.append(dict(time=time,triangle=i,deficit=deficit));continue
            needed=2*deficit+1e-6
            if needed>LIMIT:capped+=1
            for endpoint in times[index:index+2]:
                values=margins.setdefault(endpoint,[0.]*len(triangles))
                values[i]=max(values[i],min(LIMIT,needed))
    return margins,dict(profile='measured-boundary-endpoint-headroom-v1-experiment',
        key_count=len(margins),limit=LIMIT,capped_observations=capped,fixed_unresolved=fixed,
        authority='none',selected=False,scope='solver_targets_only_acceptance_floors_unchanged')
