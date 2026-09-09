"""Ownership-scoped diagnostic meshes; isolated alpha never changes source PNGs."""
import hashlib
from io import BytesIO

from .component_partitions import validate as validate_partition
from .component_weight_samples import build as sample_weights
from ..joints.partition_mesh import build_region
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.component-mesh-candidates/v1'
PROFILE = 'component-isolated-grid-joint-plane-v1'


def isolated_png(raw, region):
    from PIL import Image
    with Image.open(BytesIO(raw)) as source:
        rgba = source.convert('RGBA')
    # Keep RGB exactly; only the diagnostic alpha plane is restricted to this region.
    original = rgba.getchannel('A').tobytes()
    mask = bytearray(len(original))
    width = rgba.width
    for y, start, end in region['runs']:
        offset = y*width
        mask[offset+start:offset+end] = original[offset+start:offset+end]
    rgba.putalpha(Image.frombytes('L', rgba.size, bytes(mask)))
    output = BytesIO(); rgba.save(output, format='PNG')
    return output.getvalue()


def build(entries, skeleton, draft, addresses, plan_sha):
    for layer, raw, candidate, _ in entries:
        validate_partition(layer, raw, candidate)
    checks = sample_weights(entries, skeleton, draft, addresses, plan_sha)
    lookup = {(layer['layer_id'], region['id']): (layer, raw, region)
              for layer, raw, candidate, _ in entries
              for region in candidate['components'] + [candidate['residual']]}
    rows = []
    for check in checks['records']:
        layer, raw, region = lookup[check['layer_id'], check['component_id']]
        row = dict(layer_id=check['layer_id'], component_id=check['component_id'],
                   status='blocked', reason_codes=[check['reason_code']], mesh=None,
                   source_image_sha256=hashlib.sha256(raw).hexdigest(), isolated_image_sha256=None)
        if check['status'] == 'sampled_candidate':
            image = isolated_png(raw, region)
            side = check['bone_ids'][0][-1]
            mesh = build_region(image, layer, side, check['bone_ids'], skeleton)
            # IDs must distinguish multiple connected components of the same source and side.
            mesh['layer_id'] = layer['layer_id'] + '-' + region['id']
            row.update(status=mesh['status'], reason_codes=mesh['reason_codes'], mesh=mesh,
                       isolated_image_sha256=hashlib.sha256(image).hexdigest())
        rows.append(row)
    return dict(schema=SCHEMA, profile=PROFILE, project_id=draft['project_id'],
                sources=draft['sources'], draft_sha256=canonical_sha256(draft),
                skeleton_sha256=canonical_sha256(skeleton), weight_checks_sha256=canonical_sha256(checks),
                texture_policy='isolated_alpha_diagnostic_only', seam_status='not_evaluated',
                runtime_status='not_evaluated', records=rows, authority='none', production_authorized=False)


def validate(document, entries, skeleton, draft, addresses, plan_sha):
    if canonical_sha256(document) != canonical_sha256(build(entries, skeleton, draft, addresses, plan_sha)):
        raise ValueError('component_mesh_mismatch')
    return document
