"""Candidate depth on known skeletal segments, never fabricated garment depth."""
import math

from ..spine43.seam_raster import mask

PROFILE = 'weighted-segment-depth-proxy-v1'


def vertex_depths(document, attachment, segments):
    """Interpolate source endpoint depths along each influence's setup bone axis.

    Missing bones, out-of-segment influences and non-normalized weights abstain.
    The planar cross-section assumption is explicit: this is not measured skin Z.
    """
    data = attachment.get('vertices', [])
    if attachment.get('type') != 'mesh' or len(data) == len(attachment.get('uvs', [])):
        raise ValueError('depth_proxy_weighted_mesh_required')
    values = []; cursor = 0
    while cursor < len(data):
        count = data[cursor]; cursor += 1
        if type(count) is not int or count < 1 or cursor+count*4 > len(data):
            raise ValueError('depth_proxy_weights_invalid')
        total = 0.; z = 0.; known = True
        for _ in range(count):
            index, x, y, weight = data[cursor:cursor+4]; cursor += 4
            if (type(index) is not int or not 0 <= index < len(document['bones'])
                    or not all(math.isfinite(v) for v in (x,y,weight)) or weight < 0):
                raise ValueError('depth_proxy_weights_invalid')
            total += weight
            if weight == 0:
                continue
            bone = document['bones'][index]; length = bone.get('length', 0)
            segment = segments.get(bone['name'])
            if segment is None or length <= 0 or not 0 <= x <= length:
                known = False
                continue
            a,b = segment
            if not all(math.isfinite(v) for v in (a,b,length)):
                raise ValueError('depth_proxy_segment_invalid')
            z += weight*(a+(b-a)*x/length)
        values.append(z if known and abs(total-1) <= 1e-6 else None)
    if len(values)*2 != len(attachment['uvs']):
        raise ValueError('depth_proxy_vertex_count_invalid')
    return values


def overlap_support(probe, arm, torso, time, segments, *, margin=.02):
    """Classify opaque overlap with conservative per-triangle depth bounds."""
    import numpy as np
    if not math.isfinite(margin) or margin <= 0:
        raise ValueError('depth_proxy_margin_invalid')
    pair = probe.pair(arm,torso,time)
    result = dict(profile=PROFILE,authority='none',selected=False,time=time,pair=[arm,torso],
                  overlap_pixels=pair['overlap_pixels'],margin=margin,
                  assumption='source_segment_axis_depth_with_planar_cross_sections',
                  scope='candidate_proxy_not_measured_surface_depth_or_order_acceptance')
    if not pair['overlap_pixels']:
        return dict(result,status='no_overlap',counts={})
    rect=pair['roi']; area=rect[2]*rect[3]
    attachments={n:probe.document['skins'][0]['attachments'][n][probe.slots[n]['attachment']] for n in (arm,torso)}
    def raster(name,attachment):
        if probe.remaining < area:
            raise ValueError('depth_overlap_pixel_budget')
        probe.remaining -= area
        return mask(attachment,probe.positions[time][name],probe.textures[name],rect)>=8
    common=raster(arm,attachments[arm]) & raster(torso,attachments[torso])
    values=vertex_depths(probe.document,attachments[arm],segments)
    flat=attachments[arm]['triangles']; groups={k:[] for k in ('front','back','ambiguous','unknown')}
    for i in range(0,len(flat),3):
        tri=flat[i:i+3]; depths=[values[v] for v in tri]
        group=('unknown' if any(v is None for v in depths) else
               'front' if min(depths)>margin else 'back' if max(depths)<-margin else 'ambiguous')
        groups[group].extend(tri)
    masks={k:raster(arm,dict(attachments[arm],triangles=indices)) & common
           if indices else np.zeros_like(common) for k,indices in groups.items()}
    unknown=masks['unknown'] | (common & ~np.logical_or.reduce(list(masks.values())))
    ambiguous=(masks['ambiguous'] | (masks['front'] & masks['back'])) & ~unknown
    front=masks['front'] & ~unknown & ~ambiguous
    back=masks['back'] & ~unknown & ~ambiguous
    counts={k:int(v.sum()) for k,v in dict(front=front,back=back,ambiguous=ambiguous,unknown=unknown).items()}
    status=('uniform_front_proxy' if counts['front']==pair['overlap_pixels'] else
            'uniform_back_proxy' if counts['back']==pair['overlap_pixels'] else 'requires_partition_or_more_depth')
    return dict(result,status=status,counts=counts)
