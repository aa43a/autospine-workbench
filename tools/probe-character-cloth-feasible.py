"""Fit one recorded cloth pose under hard geometry and material limits."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.asset.planning.cloth_feasible_target import fit
from autospine_workbench.asset.planning.component_local_solver import metrics


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); data=json.loads(args.probe.read_bytes())
    bundle=AnimatedStore(args.state_root).read(data['previous'])
    frames=json.loads(bundle['numeric-reference.json'])['animations']['wave-left']
    frame=next(f for f in frames if f['time']==data['time'])
    seed=frame['vertices'][data['helper'][6:]]
    free=data['records'][0]['solver']['free_vertices']
    points,info=fit(data['setup'],data['triangles'],data['fixed'],free,data['target'],seed)
    info.update(source=data['source'],seed_bundle=data['previous'],time=data['time'],helper=data['helper'],
                geometry=metrics(data['setup'],points,data['triangles']),points=points)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(canonical_bytes(info))
    print(json.dumps({k:v for k,v in info.items() if k!='points'}),flush=True)


if __name__=='__main__': main()
