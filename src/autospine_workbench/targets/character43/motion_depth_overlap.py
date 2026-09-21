"""Bounded same-frame native-pixel alpha overlap for source depth candidates."""
from copy import deepcopy
import math

from .affine_pose import sample
from ..spine43.seam_raster import mask, texture

PROFILE = 'external-depth-native-alpha-overlap-v1'
SPARSE_PROFILE = 'external-depth-sparse-alpha-overlap-v1-experiment'
SPARSE_DEPTH_PROFILE = 'external-arm-torso-depth-sparse-v1-experiment'


class RasterBudgetError(ValueError):
    def __init__(self,a,b,time,rect,remaining,*,max_roi=262144):
        super().__init__('depth_overlap_pixel_budget')
        area=rect[2]*rect[3]
        self.diagnostic=dict(pair=[a,b],time=time,roi=rect,roi_pixels=area,
            remaining_pixels=remaining,required_pixels=area*2,
            limit_kind='single_roi' if max_roi is not None and area>max_roi else 'aggregate_budget',max_roi_pixels=max_roi)


def intersection(a, b):
    if not a or not b:
        return None
    left = math.floor(max(min(p[0] for p in a), min(p[0] for p in b)))
    right = math.ceil(min(max(p[0] for p in a), max(p[0] for p in b)))
    top = math.floor(max(min(-p[1] for p in a), min(-p[1] for p in b)))
    bottom = math.ceil(min(max(-p[1] for p in a), max(-p[1] for p in b)))
    return [left, top, right-left, bottom-top] if right > left and bottom > top else None


class Probe:
    def __init__(self, document, files, animation, *, pixel_budget=64_000_000, rendered_bounds=False,tiled=False,sparse=False):
        self.document, self.files, self.animation = document, files, animation
        self.remaining = pixel_budget
        self.rendered_bounds = rendered_bounds
        self.tiled=tiled
        self.sparse=sparse
        if sparse and not tiled:raise ValueError('depth_sparse_requires_tiled')
        self.slots = {s['name']: s for s in document['slots']}
        self.textures = {}; self.positions = {}; self.results = {}
        self._alpha_key=None; self._alpha_tiles={}

    def cached_common(self,a,b,time,rect):
        if self._alpha_key==(min(a,b),max(a,b),time):
            return self._alpha_tiles.get(tuple(rect))
        return None

    def reuse(self,other):
        """Reuse completed measurements only, under identical in-memory inputs."""
        if (self.document is not other.document or self.files is not other.files or
                self.animation!=other.animation or self.rendered_bounds!=other.rendered_bounds or
                self.tiled!=other.tiled or self.sparse!=other.sparse):
            raise ValueError('depth_overlap_cache_identity')
        if any(k in self.results and self.results[k]!=v for k,v in other.results.items()):
            raise ValueError('depth_overlap_cache_conflict')
        count=len(other.results.keys()-self.results.keys())
        self.results.update(deepcopy(other.results))
        return count

    def pair(self, a, b, time):
        if self.document['animations'][self.animation].get('slots'):
            raise ValueError('depth_overlap_attachment_unsupported')
        key = (min(a, b), max(a, b), time)
        if key in self.results:
            return self.results[key]
        if time not in self.positions:
            if len(self.positions) >= 1025:
                raise ValueError('depth_overlap_frame_limit')
            self.positions[time] = sample(self.document, self.animation, time)[0]
        points = self.positions[time]
        attachments = []
        for name in (a, b):
            slot = self.slots[name]
            attachment = self.document['skins'][0]['attachments'][name][slot['attachment']]
            if (slot.get('blend', 'normal') != 'normal' or slot.get('color', 'ffffffff') != 'ffffffff'
                    or attachment.get('type') != 'mesh' or attachment.get('color', 'ffffffff') != 'ffffffff'):
                raise ValueError('depth_overlap_attachment_unsupported')
            if name not in self.textures:
                self.textures[name] = texture(self.files['images/'+attachment.get('path', slot['attachment'])+'.png'])
            attachments.append(attachment)
        bounds=[]
        for name,attachment in zip((a,b),attachments):
            indices=attachment.get('triangles',[])
            if self.rendered_bounds:
                if len(indices)%3 or any(type(i) is not int or not 0<=i<len(points[name]) for i in indices):
                    raise ValueError('depth_overlap_triangle_indices_invalid')
                bounds.append([points[name][i] for i in sorted(set(indices))])
            else: bounds.append(points[name])
        rect = intersection(*bounds)
        if rect is None:
            result = dict(status='sampled', overlap_pixels=0, roi=None)
        else:
            area = rect[2]*rect[3]
            from .depth_raster_tiles import tiles
            if self.sparse:
                from .depth_sparse_tiles import regions as sparse_regions
                regions=sparse_regions(rect,attachments,[points[a],points[b]])
                area=sum(r[2]*r[3] for r in regions)
            else:regions=tiles(rect) if self.tiled else [rect]
            if (area > 262144 and not self.tiled) or area*2 > self.remaining:
                error=RasterBudgetError(a,b,time,rect,self.remaining,max_roi=None if self.tiled else 262144)
                if self.sparse:error.diagnostic.update(required_pixels=area*2,
                    sampled_roi_pixels=area,profile='conservative-triangle-box-tiles-v1-experiment')
                raise error
            self.remaining -= area*2
            measurements=[]
            if self.tiled: self._alpha_key=key; self._alpha_tiles={}
            for region in regions:
                first = mask(attachments[0], points[a], self.textures[a], region) >= 8
                second = mask(attachments[1], points[b], self.textures[b], region) >= 8
                common=first&second
                measurements.append(dict(status='sampled',overlap_pixels=int(common.sum()),roi=region))
                if self.tiled:
                    common.flags.writeable=False
                    self._alpha_tiles[tuple(region)]=common
            result = dict(status='sampled', overlap_pixels=sum(r['overlap_pixels'] for r in measurements), roi=rect)
            if self.tiled: result['tiles']=measurements
            if self.sparse:result['sampled_roi_pixels']=area
        self.results[key] = result
        return result


def inspect(document, files, animation, depth, *, sparse=False):
    report = deepcopy(depth)
    probe = Probe(document, files, animation, sparse=sparse, tiled=sparse, rendered_bounds=sparse)
    pending = unmeasured = visible = ambiguous = 0
    for pair in report['pairs']:
        for row in pair['samples']:
            try:
                overlap = probe.pair(pair['arm_slot'], pair['torso_slot'], row['tick']/1e6)
            except ValueError as exc:
                overlap = dict(status='unmeasured', reason_code=str(exc))
                if getattr(exc, 'diagnostic', None):
                    overlap['raster_budget'] = exc.diagnostic
                unmeasured += 1
            row['overlap'] = overlap
            if overlap.get('overlap_pixels', 0) > 0:
                visible += 1
                if row['ambiguous']:
                    ambiguous += 1
                elif row['current_front_slot'] != pair['setup_front_slot']:
                    pending += 1
    report['target_overlap'] = dict(profile=SPARSE_PROFILE if sparse else PROFILE, visible_pair_samples=visible,
        ambiguous_visible_pair_samples=ambiguous, order_mismatch_pair_samples=pending,
        unmeasured_pair_samples=unmeasured, alpha_threshold=8, pixel_budget=64_000_000,
        sampled_pixel_budget_used=64_000_000-probe.remaining,
        scope='cpu_native_pixel_centres_bilinear_alpha_not_gpu_or_continuous_time')
    return report, probe
