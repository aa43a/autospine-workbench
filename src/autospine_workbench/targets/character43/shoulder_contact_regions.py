"""Prepare source-supported shoulder regions and solve one bounded pose."""
import numpy as np
from .shoulder_boundary import prepare
from .alpha_contact_disks import disks
from .boundary_shape_feasible import refine


def prepare_regions(row):
    context=prepare(row['points'],row['triangles'],row['contact'],row['root'],row['distal'])
    support=[];locked=[]
    for v in context['pins']:
        try:support.append(dict(vertex=v,**disks(row['contact'],[row['points'][v]],context['spacing_px'])[0]))
        except ValueError as e:
            if str(e)!='alpha_contact_disk_no_supported_interior':raise
            locked.append(v)
    return dict(context=context,support=support,locked=locked,free=context['free']+[r['vertex'] for r in support])


def constraints(row,prepared,rest,current,world):
    R=np.array([[rest[0],rest[1]],[rest[2],rest[3]]]);C=np.array([[current[0],current[1]],[current[2],current[3]]]);A=C@np.linalg.inv(R)
    fixed=[p[:] for p in world];regions=[]
    for v in prepared['locked']:fixed[v]=(A@(np.array(row['points'][v])-rest[4:])+current[4:]).tolist()
    for disk in prepared['support']:
        center=A@(np.array(disk['center'])-rest[4:])+current[4:]
        regions.append(dict(vertex=disk['vertex'],center=center.tolist(),inverse=np.linalg.inv(A).tolist(),radius=disk['radius']))
    return fixed,regions


def solve(row,prepared,rest,current,world,previous=None,*,region_margin=1e-5):
    fixed,regions=constraints(row,prepared,rest,current,world)
    seed=[p[:] for p in world] if previous is None else (np.asarray(previous[1])+np.asarray(world)-previous[0]).tolist()
    for v in prepared['locked']:seed[v]=fixed[v][:]
    if previous is None:
        for region in regions:seed[region['vertex']]=region['center'][:]
    points,report=refine(row['points'],row['triangles'],fixed,prepared['free'],world,seed,
                         prepared['context']['budget_px'],regions=regions,region_margin=region_margin)
    # Never bake an unchecked warm-start seed when a solve failed.
    return (points if report['status']=='feasible_candidate' else world),report
