"""Bounded same-frame native-pixel alpha overlap for source depth candidates."""
from copy import deepcopy
import math

from .affine_pose import sample
from ..spine43.seam_raster import mask, texture

PROFILE = 'external-depth-native-alpha-overlap-v1'


def intersection(a, b):
    if not a or not b:
        return None
    left = math.floor(max(min(p[0] for p in a), min(p[0] for p in b)))
    right = math.ceil(min(max(p[0] for p in a), max(p[0] for p in b)))
    top = math.floor(max(min(-p[1] for p in a), min(-p[1] for p in b)))
    bottom = math.ceil(min(max(-p[1] for p in a), max(-p[1] for p in b)))
    return [left, top, right-left, bottom-top] if right > left and bottom > top else None


class Probe:
    def __init__(self, document, files, animation, *, pixel_budget=64_000_000, rendered_bounds=False):
        self.document, self.files, self.animation = document, files, animation
        self.remaining = pixel_budget
        self.rendered_bounds = rendered_bounds
        self.slots = {s['name']: s for s in document['slots']}
        self.textures = {}; self.positions = {}; self.results = {}

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
            if area > 262144 or area*2 > self.remaining:
                raise ValueError('depth_overlap_pixel_budget')
            self.remaining -= area*2
            first = mask(attachments[0], points[a], self.textures[a], rect) >= 8
            second = mask(attachments[1], points[b], self.textures[b], rect) >= 8
            result = dict(status='sampled', overlap_pixels=int((first & second).sum()), roi=rect)
        self.results[key] = result
        return result


def inspect(document, files, animation, depth):
    report = deepcopy(depth)
    probe = Probe(document, files, animation)
    pending = unmeasured = visible = ambiguous = 0
    for pair in report['pairs']:
        for row in pair['samples']:
            try:
                overlap = probe.pair(pair['arm_slot'], pair['torso_slot'], row['tick']/1e6)
            except ValueError as exc:
                overlap = dict(status='unmeasured', reason_code=str(exc))
                unmeasured += 1
            row['overlap'] = overlap
            if overlap.get('overlap_pixels', 0) > 0:
                visible += 1
                if row['ambiguous']:
                    ambiguous += 1
                elif row['current_front_slot'] != pair['setup_front_slot']:
                    pending += 1
    report['target_overlap'] = dict(profile=PROFILE, visible_pair_samples=visible,
        ambiguous_visible_pair_samples=ambiguous, order_mismatch_pair_samples=pending,
        unmeasured_pair_samples=unmeasured, alpha_threshold=8, pixel_budget=64_000_000,
        sampled_pixel_budget_used=64_000_000-probe.remaining,
        scope='cpu_native_pixel_centres_bilinear_alpha_not_gpu_or_continuous_time')
    return report, probe
