"""Inspect exact same-source residual pixel coverage by existing weighted meshes."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.residual_mesh_support import inspect


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    p.add_argument('--bundle',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();report=inspect(AnimatedStore(args.state_root).read(args.bundle))
    report['bundle_sha256']=args.bundle
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical_bytes(report))
    print(json.dumps([dict(region=r['region_id'],counts=r['counts']) for r in report['rows']]))
