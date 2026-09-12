"""Inspect a direction target against fixed-boundary mesh-path stretch bounds."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.drape_direction import apply
from autospine_workbench.asset.planning.cloth_reachability import inspect


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    p.add_argument('--wave',required=True);p.add_argument('--helper',required=True)
    p.add_argument('--animation',default='wave-left');p.add_argument('--time',type=float,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if not math.isfinite(args.time) or args.time<0:
        p.error('--time must be finite and nonnegative')
    doc=json.loads(AnimatedStore(args.state_root).read(args.wave)['skeleton.json'])
    held,_=apply(doc,args.animation,[args.helper]);slot=args.helper.removeprefix('cloth-')
    attachment=doc['skins'][0]['attachments'][slot][slot];vertices=attachment['vertices']
    free=[];cursor=0;index=0
    while cursor<len(vertices):
        count=vertices[cursor];cursor+=1;weight=0.
        for _ in range(count):
            bone,_,_,w=vertices[cursor:cursor+4];cursor+=4
            if doc['bones'][bone]['name']==args.helper:weight+=w
        if weight>1e-7:free.append(index)
        index+=1
    flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
    setup=sample(doc,args.animation,0)[0][slot]
    fixed=sample(doc,args.animation,args.time)[0][slot];target=sample(held,args.animation,args.time)[0][slot]
    report=inspect(setup,fixed,triangles,free,target)
    report.update(source_wave_sha256=args.wave,helper=args.helper,animation=args.animation,time=args.time)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k not in {'records','anchor_vertices'}}))


if __name__=='__main__':main()
