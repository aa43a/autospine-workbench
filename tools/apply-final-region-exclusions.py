"""Apply an explicitly confirmed exact residual scope after candidate transforms."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--confirmation',type=Path,required=True)
    parser.add_argument('--character',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); confirmation_bytes=args.confirmation.read_bytes()
    confirmation=json.loads(confirmation_bytes)
    if confirmation.get('decision_source')!='human_confirmation':
        raise ValueError('character_final_confirmation_required')
    rows=[r for r in confirmation['scope'] if r['character']==args.character]
    if not rows or len({r['artifact_sha256'] for r in rows})!=1:
        raise ValueError('character_final_confirmation_scope')
    digest=rows[0]['artifact_sha256']; store=AnimatedStore(args.state_root); files=store.read(digest)
    decisions=[dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',
        source_bundle_sha256=digest,manifest_sha256=sha256(files['character-manifest.json']).hexdigest(),
        layer_id=r['layer_id'],region_id=r['region_id'],image_sha256=r['source_sha256'],reversible=True)
        for r in rows]
    output=apply_batch(files,decisions)
    receipt=dict(source_bundle_sha256=digest,bundle_sha256=store.publish(output),
        excluded_regions=sorted(r['region_id'] for r in rows),
        confirmation_sha256=sha256(confirmation_bytes).hexdigest(),
        authority='none',production_authorized=False,runtime_status='not_run')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'generation.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
