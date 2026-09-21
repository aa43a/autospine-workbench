"""Candidate depth on known skeletal segments, never fabricated garment depth."""
import math

from ..spine43.seam_raster import mask

PROFILE = 'weighted-segment-depth-proxy-v1'
CAP_PROFILE = 'weighted-segment-quarter-cap-depth-proxy-v1'


def vertex_depths(document, attachment, segments, *, endpoint_caps=False, axis_lengths=None):
    """Interpolate source endpoint depths along each influence's setup bone axis.

    Missing bones, out-of-segment influences and non-normalized weights abstain.
    The planar cross-section assumption is explicit: this is not measured skin Z.
    """
    axis_lengths=axis_lengths or {}
    if any(n not in ('hand_l','hand_r') or not math.isfinite(v) or v<=0 for n,v in axis_lengths.items()):
        raise ValueError('depth_proxy_hand_axis_invalid')
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
            bone = document['bones'][index]; length = axis_lengths.get(bone['name'],bone.get('length', 0))
            segment = segments.get(bone['name'])
            extension = .25*length if endpoint_caps else 0
            if segment is None or length <= 0 or not -extension <= x <= length+extension:
                known = False
                continue
            a,b = segment
            if not all(math.isfinite(v) for v in (a,b,length)):
                raise ValueError('depth_proxy_segment_invalid')
            coordinate = min(length,max(0,x)) if endpoint_caps else x
            z += weight*(a+(b-a)*coordinate/length)
        values.append(z if known and abs(total-1) <= 1e-6 else None)
    if len(values)*2 != len(attachment['uvs']):
        raise ValueError('depth_proxy_vertex_count_invalid')
    return values


def overlap_support(probe, arm, torso, time, segments, *, margin=.02, endpoint_caps=False, reference_plane=None, axis_lengths=None, depth_intervals=None, pixelwise=False, on_triangle=None):
    """Classify opaque overlap with conservative per-triangle depth bounds."""
    import numpy as np
    if not math.isfinite(margin) or margin <= 0:
        raise ValueError('depth_proxy_margin_invalid')
    if reference_plane is not None and (len(reference_plane)!=3 or not all(math.isfinite(v) for v in reference_plane)):
        raise ValueError('depth_proxy_plane_invalid')
    pair = probe.pair(arm,torso,time)
    result = dict(profile=CAP_PROFILE if endpoint_caps else PROFILE,authority='none',selected=False,time=time,pair=[arm,torso],
                  overlap_pixels=pair['overlap_pixels'],margin=margin,
                  endpoint_extension_ratio=.25 if endpoint_caps else 0,
                  assumption='source_segment_axis_depth_with_planar_cross_sections',
                  scope='candidate_proxy_not_measured_surface_depth_or_order_acceptance')
    if reference_plane is not None:
        result.update(profile='weighted-segment-versus-garment-plane-v1-experiment',
                      reference_plane=list(reference_plane),
                      assumption='source_segment_axis_depth_against_explicit_planar_garment_proxy')
    if axis_lengths:
        result.update(profile='weighted-mesh-hand-axis-depth-v1-experiment',hand_axis_lengths=dict(axis_lengths))
    if depth_intervals is not None:
        result.update(profile='weighted-depth-interval-overlap-v1-experiment',
                      uncertainty_policy='entire_interval_must_clear_margin')
    if pixelwise:
        result.update(profile='barycentric-pixel-depth-interval-v1-experiment',
                      spatial_sampling='opaque_native_pixel_centres_linear_vertex_depth_intervals')
    if not pair['overlap_pixels']:
        return dict(result,status='no_overlap',counts={})
    if 'tiles' in pair:
        from .depth_raster_tiles import TileProbe
        counts={k:0 for k in ('front','back','ambiguous','unknown')}
        for tile in pair['tiles']:
            if not tile['overlap_pixels']: continue
            part=overlap_support(TileProbe(probe,tile),arm,torso,time,segments,margin=margin,
                endpoint_caps=endpoint_caps,reference_plane=reference_plane,axis_lengths=axis_lengths,depth_intervals=depth_intervals,pixelwise=pixelwise,on_triangle=on_triangle)
            for key,value in part['counts'].items(): counts[key]+=value
        status=('uniform_front_proxy' if counts['front']==pair['overlap_pixels'] else
                'uniform_back_proxy' if counts['back']==pair['overlap_pixels'] else 'requires_partition_or_more_depth')
        return dict(result,status=status,counts=counts,raster_policy='native_pixel_tiles_256_v1')
    rect=pair['roi']; area=rect[2]*rect[3]
    attachments={n:probe.document['skins'][0]['attachments'][n][probe.slots[n]['attachment']] for n in (arm,torso)}
    def raster(name,attachment):
        if probe.remaining < area:
            raise ValueError('depth_overlap_pixel_budget')
        probe.remaining -= area
        return mask(attachment,probe.positions[time][name],probe.textures[name],rect)>=8
    common=probe.cached_common(arm,torso,time,rect)
    if common is None: common=raster(arm,attachments[arm]) & raster(torso,attachments[torso])
    values=vertex_depths(probe.document,attachments[arm],segments,endpoint_caps=endpoint_caps,axis_lengths=axis_lengths)
    intervals=([[v,v] if v is not None else None for v in values] if depth_intervals is None else depth_intervals)
    if len(intervals)!=len(values) or any(v is not None and (len(v)!=2 or not all(math.isfinite(z) for z in v)
                                                            or v[0]>v[1]) for v in intervals):
        raise ValueError('depth_proxy_intervals_invalid')
    if reference_plane is not None:
        dx,dy,offset=reference_plane
        intervals=[None if v is None else [z-dx*p[0]-dy*p[1]-offset for z in v]
                   for v,p in zip(intervals,probe.positions[time][arm])]
    if pixelwise:
        from .depth_pixel_intervals import classify
        def charge(amount):
            if probe.remaining<amount:raise ValueError('depth_overlap_pixel_budget')
            probe.remaining-=amount
        counts=classify(attachments[arm],probe.positions[time][arm],probe.textures[arm],rect,
                        common,intervals,margin,charge,on_triangle=on_triangle)
        status=('uniform_front_proxy' if counts['front']==pair['overlap_pixels'] else
                'uniform_back_proxy' if counts['back']==pair['overlap_pixels'] else 'requires_partition_or_more_depth')
        return dict(result,status=status,counts=counts)
    flat=attachments[arm]['triangles']; groups={k:[] for k in ('front','back','ambiguous','unknown')}
    for i in range(0,len(flat),3):
        tri=flat[i:i+3]; depths=[intervals[v] for v in tri]
        group=('unknown' if any(v is None for v in depths) else
               'front' if min(v[0] for v in depths)>margin else 'back' if max(v[1] for v in depths)<-margin else 'ambiguous')
        groups[group].extend(tri)
    def group_raster(indices,support=common):
        attachment=dict(attachments[arm],triangles=indices)
        if getattr(probe,'sparse',False) in ('tight_depth_groups','common_depth_points','priority_depth_points'):
            from .depth_group_raster import raster as cropped
            if probe.sparse in ('common_depth_points','priority_depth_points'):
                from .depth_common_raster import raster as cropped
            def charge(amount):
                if probe.remaining<amount:raise ValueError('depth_overlap_pixel_budget')
                probe.remaining-=amount
            return cropped(attachment,probe.positions[time][arm],probe.textures[arm],rect,support,charge)
        return raster(arm,attachment)
    if getattr(probe,'sparse',False)=='priority_depth_points':
        masks={};support=common.copy()
        for kind in ('unknown','ambiguous','front','back'):
            masks[kind]=group_raster(groups[kind],support)&support if groups[kind] else np.zeros_like(common)
            # Unknown dominates ambiguous, which dominates either known direction.
            # Front and back must still be evaluated on the same remaining pixels.
            if kind in ('unknown','ambiguous'):support &= ~masks[kind]
    else:
        masks={k:group_raster(indices) & common
               if indices else np.zeros_like(common) for k,indices in groups.items()}
    unknown=masks['unknown'] | (common & ~np.logical_or.reduce(list(masks.values())))
    ambiguous=(masks['ambiguous'] | (masks['front'] & masks['back'])) & ~unknown
    front=masks['front'] & ~unknown & ~ambiguous
    back=masks['back'] & ~unknown & ~ambiguous
    counts={k:int(v.sum()) for k,v in dict(front=front,back=back,ambiguous=ambiguous,unknown=unknown).items()}
    status=('uniform_front_proxy' if counts['front']==pair['overlap_pixels'] else
            'uniform_back_proxy' if counts['back']==pair['overlap_pixels'] else 'requires_partition_or_more_depth')
    return dict(result,status=status,counts=counts)
