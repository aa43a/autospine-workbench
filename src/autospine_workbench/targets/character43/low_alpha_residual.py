"""Source-bound exclusion policy for residual-only, nearly transparent textures."""
from hashlib import sha256
import json
from ...png_rgba import decode_rgba_png
from ...resolved_project import canonical_sha256

PROFILE='low-alpha-residual-v1'


def propose(files):
    manifest=json.loads(files['character-manifest.json']);doc=json.loads(files['skeleton.json'])
    source=canonical_sha256({n:sha256(raw).hexdigest() for n,raw in files.items()})
    rows=[]
    for layer in manifest['layers']:
        regions=layer.get('regions',[])
        if not any(r['state']=='weighted_candidate' for r in regions):continue
        for region in regions:
            key=region['region_id']
            if region['state']!='static_reference' or key!=layer['layer_id']+'-residual':continue
            attachment=doc['skins'][0]['attachments'][key][key]
            raw=files['images/'+attachment.get('path',key)+'.png']
            alpha=decode_rgba_png(raw).pixels[3::4]
            if not any(alpha) or max(alpha)>=8:continue
            rows.append(dict(schema='autospine.region-exclusion/v2',decision_source='policy_auto',policy_id=PROFILE,
                source_bundle_sha256=source,manifest_sha256=sha256(files['character-manifest.json']).hexdigest(),
                layer_id=layer['layer_id'],region_id=key,image_sha256=sha256(raw).hexdigest(),
                visible_pixels=sum(a>0 for a in alpha),max_alpha=max(alpha),reversible=True))
    return rows


def validate(files,decision):
    expected=next((r for r in propose(files) if r['region_id']==decision.get('region_id')),None)
    # Batch compilation adds provenance only; the active decision remains exact.
    value={k:v for k,v in decision.items() if k!='scope_replay'}
    if expected is None or canonical_sha256(expected)!=canonical_sha256(value):
        raise ValueError('low_alpha_residual_policy_invalid')
