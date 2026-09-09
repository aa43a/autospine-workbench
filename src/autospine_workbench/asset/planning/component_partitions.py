"""Unowned, disjoint alpha components using the original shared texture."""
from array import array
from collections import deque
from hashlib import sha256
from io import BytesIO

from ...resolved_project import canonical_sha256
from ...manifest_artifacts import require_sha256
from ..joints.partition_pixels import neighbors

PROFILE = 'unowned-alpha-components-v1'
MAX_PIXELS = 4 * 1024 * 1024


def build(layer, raw):
    from PIL import Image
    require_sha256(layer['image_sha256'], 'Layer image')
    if type(raw) is not bytes or len(raw) > 128 * 1024 * 1024 or sha256(raw).hexdigest() != layer['image_sha256']:
        raise ValueError('component_partition_image_changed')
    with Image.open(BytesIO(raw)) as image:
        w, h = image.size
        x, y, right, bottom = layer['bbox']
        if image.format != 'PNG' or image.mode != 'RGBA' or (w, h) != (right-x, bottom-y):
            raise ValueError('component_partition_image_invalid')
        if w*h > MAX_PIXELS:
            raise ValueError('component_partition_resource_limit')
        alpha = image.tobytes()[3::4]
    labels = array('i', [-1]) * (w*h)
    parts = []
    for start, a in enumerate(alpha):
        if a < 8 or labels[start] != -1:
            continue
        if len(parts) >= 4096:
            raise ValueError('component_partition_resource_limit')
        label = len(parts); labels[start] = label
        queue = deque([start]); count = 0
        left = right = start % w; top = bottom = start // w
        while queue:
            index = queue.popleft(); count += 1
            px, py = index % w, index // w
            left, right = min(left, px), max(right, px)
            top, bottom = min(top, py), max(bottom, py)
            for near in neighbors(index, w, w*h):
                if labels[near] == -1 and alpha[near] >= 8:
                    labels[near] = label; queue.append(near)
        parts.append(dict(id=f'component-{label:04d}', owner=None, bone_ids=[],
                          pixel_count=count, bbox=[left+x, top+y, right+x+1, bottom+y+1], runs=[]))
    residual = dict(id='low-alpha-residual', owner=None, bone_ids=[], pixel_count=0, runs=[])
    runs = 0
    for py in range(h):
        px = 0
        while px < w:
            index = py*w+px
            if not alpha[index]:
                px += 1; continue
            owner = labels[index]
            end = px+1
            while end < w and alpha[py*w+end] and labels[py*w+end] == owner:
                end += 1
            row = parts[owner] if owner >= 0 else residual
            row['runs'].append([py, px, end])
            if owner < 0:
                residual['pixel_count'] += end-px
            runs += 1
            if runs > 131072:
                raise ValueError('component_partition_resource_limit')
            px = end
    visible = sum(a > 0 for a in alpha)
    if sum(p['pixel_count'] for p in parts) + residual['pixel_count'] != visible:
        raise ValueError('component_partition_coverage_invalid')
    return dict(schema='autospine.component-partition-candidate/v1', profile=PROFILE,
                layer_id=layer['layer_id'], image_sha256=layer['image_sha256'],
                bbox=layer['bbox'][:], run_coordinates='layer_local_half_open',
                alpha_threshold=8, connectivity=4, components=parts, residual=residual,
                visible_pixel_count=visible, visible_coverage_exact=True,
                status='needs_review' if parts else 'blocked',
                reason_code='pixel_ownership_review_required' if parts else 'opaque_component_missing',
                authority='none', production_authorized=False)


def validate(layer, raw, document):
    if canonical_sha256(build(layer, raw)) != canonical_sha256(document):
        raise ValueError('component_partition_replay_mismatch')
    return document
