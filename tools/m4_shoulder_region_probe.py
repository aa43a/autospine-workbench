"""Relax shoulder pins only within source-supported alpha disks; isolated pose test."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import ImageDraw
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_boundary import prepare
from autospine_workbench.targets.character43.alpha_contact_disks import disks
from autospine_workbench.targets.character43.boundary_shape_feasible import refine
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.skirt_contact import source_image


def run(source,output,times,shape_objective=False):
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(identity);doc,rows=contexts(files)
    rest=matrices(dict(doc,animations={'setup':{}}),'setup',0)['chest'];R=np.array([[rest[0],rest[1]],[rest[2],rest[3]]]);rows_out=[]
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    output.mkdir(parents=True,exist_ok=False)
    for row in rows:
        context=prepare(row['points'],row['triangles'],row['contact'],row['root'],row['distal'])
        support=[];unsupported=[]
        for v in context['pins']:
            try:support.append(dict(vertex=v,**disks(row['contact'],[row['points'][v]],context['spacing_px'])[0]))
            except ValueError as e:
                if str(e)!='alpha_contact_disk_no_supported_interior':raise
                unsupported.append(v)
        image,origin=source_image(files,doc,setup,row['slot']);image=image.convert('RGBA');draw=ImageDraw.Draw(image)
        def pixel(p):return (p[0]-origin[0],origin[1]-p[1])
        for p in row['contact']:draw.point(pixel(p),fill=(0,180,255,255))
        for v in context['pins']:
            x,y=pixel(row['points'][v]);color='red' if v in unsupported else 'yellow'
            draw.ellipse((x-4,y-4,x+4,y+4),outline=color,width=2);draw.text((x+4,y),str(v),fill=color)
        for disk in support:
            x,y=pixel(disk['center']);r=disk['radius'];draw.ellipse((x-r,y-r,x+r,y+r),outline='lime',width=1)
        image.save(output/(row['slot']+'-contact.png'))
        free=context['free']+[disk['vertex'] for disk in support]
        for t in times:
            current=matrices(doc,'external-motion',t)['chest'];C=np.array([[current[0],current[1]],[current[2],current[3]]]);A=C@np.linalg.inv(R)
            regions=[];world=sample(doc,'external-motion',t)[0][row['slot']];seed=[p[:] for p in world];fixed=[p[:] for p in world]
            # Unsupported pins retain their existing exact chest constraint.
            # They are never silently freed or treated as measured alpha contact.
            for v in unsupported:
                fixed[v]=(A@(np.array(row['points'][v])-rest[4:])+current[4:]).tolist();seed[v]=fixed[v][:]
            for disk in support:
                v=disk['vertex']
                center=A@(np.array(disk['center'])-rest[4:])+current[4:]
                regions.append(dict(vertex=v,center=center.tolist(),inverse=np.linalg.inv(A).tolist(),radius=disk['radius']))
                seed[v]=center.tolist()
            points,report=refine(row['points'],row['triangles'],fixed,free,world,seed,context['budget_px'],regions=regions,shape_objective=shape_objective)
            fixed_error=max((float(np.linalg.norm(np.array(p)-q)) for i,(p,q) in enumerate(zip(points,fixed)) if i not in free),default=0.)
            rows_out.append(dict(slot=row['slot'],time=t,context=context,support=support,retained_fixed_pins=unsupported,fixed_error_px=fixed_error,points=points,**report))
            print(json.dumps({k:v for k,v in rows_out[-1].items() if k not in ('points','context','support')}),flush=True)
    (output/'report.json').write_bytes(canonical_bytes(dict(source=identity,selected=False,authority='none',rows=rows_out,
        scope='alpha_supported_disks_selected_poses_not_full_seam_or_visual_acceptance')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--times',type=float,nargs='+',required=True);p.add_argument('--shape-objective',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.times,a.shape_objective)
