"""Build source-preserving connected component mount candidates in a full character."""
import argparse
from pathlib import Path
import json
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.component_mount_candidate import generate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--slot',required=True)
    parser.add_argument('--parent',action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--decision',type=Path)
    args=parser.parse_args();store=AnimatedStore(args.state_root)
    decision=json.loads(args.decision.read_bytes()) if args.decision else None
    files,report=generate(store.read(args.source),args.slot,args.parent,decision)
    digest=store.publish(files);args.output.mkdir(parents=True,exist_ok=True)
    receipt=dict(bundle_sha256=digest,report=report,authority='none',production_authorized=False)
    (args.output/'generation.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps(dict(bundle_sha256=digest,parts=[{k:v for k,v in r.items() if k!='parent_candidates'} for r in report['parts']],geometry_passed=report['geometry_passed']),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
