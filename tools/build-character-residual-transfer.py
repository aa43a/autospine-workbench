"""Publish a residual texture transfer trial without changing workbench inputs."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.residual_texture_transfer import build

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--bundle',required=True)
    args=p.parse_args();store=AnimatedStore(args.state_root);files,report=build(store.read(args.bundle))
    print(json.dumps(dict(source_bundle=args.bundle,bundle_sha256=store.publish(files),
        rows=[dict(region=r['region_id'],counts=r['counts']) for r in report['rows']],selected=False)))
