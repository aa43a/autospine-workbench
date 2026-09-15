"""Optional reversible default applied before official capture, never to old jobs."""
import json
from ..targets.character43.low_alpha_residual import PROFILE,propose
from ..targets.character43.final_region_exclusion import apply_batch


def apply(manager,request,result):
    if request.get('residual_auto_profile')!=PROFILE or not result['manifest']['layers']:return result
    files=manager.application.store.read(result['artifact_sha256'])
    # Explicit transformed ownership needs its own preserved recipe; do not supersede it.
    if any(key in files for key in ('component-mount.json','final-region-exclusion.json')):return result
    decisions=propose(files)
    if not decisions:return result
    output=apply_batch(files,decisions)
    return dict(result,artifact_sha256=manager.application.store.publish(output),
        manifest=json.loads(output['character-manifest.json']),
        residual_defaults=dict(policy_id=PROFILE,decision_source='policy_auto',reversible=True,
            source_bundle_sha256=result['artifact_sha256'],excluded_region_ids=[r['region_id'] for r in decisions]))
