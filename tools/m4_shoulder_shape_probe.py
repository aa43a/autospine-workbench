"""Test bounded shoulder shape feasibility on preserved failed trial samples."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.skirt_candidate import inverse
from autospine_workbench.targets.character43.boundary_shape_feasible import refine
from autospine_workbench.targets.character43.boundary_path_feasibility import inspect as path_bound


def run(source,trial,output,times):
    prior=json.loads((source/'report.json').read_bytes());receipt=json.loads((trial/'report.json').read_bytes())
    if receipt['source_candidate_sha256']!=prior['candidate_bundle_sha256']:raise ValueError('shape_probe_parent_mismatch')
    before=AnimatedStore(source/'isolated-store').read(prior['candidate_bundle_sha256'])
    after=AnimatedStore(trial/'isolated-store').read(receipt['candidate_bundle_sha256'])
    original,document=[json.loads(f['skeleton.json']) for f in (before,after)]
    duration=max(k['time'] for tracks in original['animations']['external-motion']['bones'].values() for keys in tracks.values() for k in keys)
    if not times or len(times)>33 or any(not math.isfinite(t) or not 0<=t<=duration for t in times):
        raise ValueError('shape_probe_times_invalid')
    if any(original[k]!=document[k] for k in ('bones','slots','skins')):raise ValueError('shape_probe_bind_mismatch')
    setup_document=dict(original,animations={'setup':{}})
    setup=sample(setup_document,'setup',0)[0];rest=matrices(setup_document,'setup',0);rows=[]
    output.mkdir(parents=True,exist_ok=False)
    for record in receipt['records']:
        if not record['solver_failures']:continue
        slot=record['slot'];context=record['context'];mesh=document['skins'][0]['attachments'][slot][slot]
        triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
        for t in times:
            world=sample(original,'external-motion',t)[0][slot]
            seed=sample(document,'external-motion',t)[0][slot];fixed=[list(p) for p in world]
            a,b,c,d,x,y=matrices(original,'external-motion',t)['chest']
            for v in context['pins']:
                u,w=inverse(rest['chest'],setup[slot][v]);fixed[v]=[a*u+b*w+x,c*u+d*w+y]
            points,evidence=refine(setup[slot],triangles,fixed,context['free'],world,seed,context['budget_px'])
            bound=path_bound(setup[slot],triangles,fixed,context['free'])
            row=dict(slot=slot,time=t,points=points,path_bound=bound,**evidence);rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='points'}),flush=True)
            (output/'report.json').write_bytes(canonical_bytes(dict(authority='none',selected=False,
                source=prior['candidate_bundle_sha256'],trial=receipt['candidate_bundle_sha256'],rows=rows)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','trial','output'):p.add_argument(name,type=Path)
    p.add_argument('--times',type=float,nargs='+',required=True)
    a=p.parse_args();run(a.source,a.trial,a.output,a.times)
