"""Conservative triangle ownership at actual opaque overlap, without adoption."""
from collections import defaultdict

from ..spine43.seam_raster import mask

PROFILE = 'depth-overlap-weight-ownership-v1'
GROUPS = {'chest': 'chest', 'upperarm_l': 'arm.left', 'forearm_l': 'arm.left',
          'hand_l': 'arm.left', 'upperarm_r': 'arm.right', 'forearm_r': 'arm.right',
          'hand_r': 'arm.right'}


def triangle_groups(document, attachment):
    data = attachment['vertices']
    if attachment.get('type') != 'mesh' or len(data) == len(attachment['uvs']):
        raise ValueError('depth_ownership_weighted_mesh_required')
    vertices = []; i = 0
    while i < len(data):
        count = data[i]; i += 1; names = set()
        for _ in range(count):
            index, _, _, weight = data[i:i+4]; i += 4
            if weight > 0:
                names.add(document['bones'][index]['name'])
        vertices.append(names)
    groups = defaultdict(list); bones = defaultdict(set)
    flat = attachment['triangles']
    for offset in range(0, len(flat), 3):
        names = set().union(*(vertices[v] for v in flat[offset:offset+3]))
        owners = {GROUPS.get(n, 'unmapped') for n in names}
        group = next(iter(owners)) if len(owners) == 1 else 'mixed'
        if not owners:
            group = 'unmapped'
        groups[group].append(offset//3)
        bones[group].update(names)
    return groups, bones


def inspect(probe, a, b, time):
    """Use a dedicated Probe: diagnostic raster cost must not change adoption."""
    pair = probe.pair(a, b, time)
    report = dict(profile=PROFILE, time=time, pair=[a, b], authority='none',
                  overlap_pixels=pair['overlap_pixels'], slots={},
                  scope='triangle_weight_ownership_not_3d_cloth_depth')
    if not pair['overlap_pixels']:
        return report
    rect = pair['roi']; area = rect[2]*rect[3]
    attachments = {n: probe.document['skins'][0]['attachments'][n][probe.slots[n]['attachment']]
                   for n in (a, b)}
    masks = {}
    for name in (a, b):
        if area > probe.remaining:
            raise ValueError('depth_overlap_pixel_budget')
        probe.remaining -= area
        masks[name] = mask(attachments[name], probe.positions[time][name], probe.textures[name], rect) >= 8
    common = masks[a] & masks[b]
    for name in (a, b):
        attachment = attachments[name]
        groups, bones = triangle_groups(probe.document, attachment)
        rows = []
        for group, triangles in sorted(groups.items()):
            if area > probe.remaining:
                raise ValueError('depth_overlap_pixel_budget')
            probe.remaining -= area
            subset = dict(attachment, triangles=[v for t in triangles for v in attachment['triangles'][t*3:t*3+3]])
            visible = mask(subset, probe.positions[time][name], probe.textures[name], rect) >= 8
            pixels = int((visible & common).sum())
            if pixels:
                rows.append(dict(group=group, overlap_pixels=pixels, bones=sorted(bones[group])))
        report['slots'][name] = dict(groups=rows,
            interpretation='group_counts_may_overlap_at_shared_edges_or_folded_triangles',
            missing_depth_evidence=any(r['group'] in ('mixed', 'unmapped') for r in rows))
    return report
