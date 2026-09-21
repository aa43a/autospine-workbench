"""Reusable isolated regional ordering pipeline, without adoption authority."""
from copy import deepcopy
from .source_depth_sampler import SegmentDepthSampler
from .depth_straddle_refine import refine
from .motion_depth_overlap import Probe
from .motion_depth_order import build as order_build


def build(document, files, animation, depth, bvh, mapping, *, yaw=0,
          partition_slots=None, cloth_constraints=False, limb_constraints=False,
          torso_plane=False, rendered_bounds=False, reuse_refinement_overlap=False,
          tiled=False, pair_budgets=False, refine_cycles=False, include_depth=False):
    original = deepcopy(document)
    partition = None
    if partition_slots:
        from .depth_region_partition import build as partition_build
        from .motion_depth import build as depth_build
        ticks = [r['source_tick'] for p in depth['pairs'] for r in p['samples']]
        if not ticks:
            raise ValueError('regional_depth_source_ticks_missing')
        document, partition = partition_build(document, partition_slots)
        depth = depth_build(document, bvh, mapping, clip_bounds=(min(ticks), max(ticks)),
                            yaw_degrees=yaw, render_regions=True)
    if cloth_constraints and partition is None:
        raise ValueError('cloth_constraints_require_partition')
    sampler = SegmentDepthSampler(bvh, mapping, yaw)
    probe = Probe(document, files, animation, rendered_bounds=rendered_bounds, tiled=tiled)
    refined, evidence = refine(document, files, animation, depth, sampler,
        torso_plane=torso_plane, rendered_bounds=rendered_bounds,
        order_probe=probe if reuse_refinement_overlap else None,
        tiled=tiled, pair_budgets=pair_budgets)
    cloth = limbs = None
    if cloth_constraints:
        from .cloth_depth_constraints import build as cloth_build
        refined, cloth = cloth_build(document, files, animation, refined, partition, sampler, order_probe=probe)
    if limb_constraints:
        from .limb_depth_constraints import build as limb_build
        refined, limbs = limb_build(document, files, animation, refined, sampler, order_probe=probe)
    candidate, order = order_build(document, animation, refined, probe, refine_cycles=refine_cycles)
    for name, result in [('cloth', cloth), ('limb', limbs)]:
        if result and result['unmeasured_samples']:
            candidate = None
            order['status'] = 'blocked'
            order['reason_codes'].append(name + '_depth_unmeasured')
    if candidate is not None:
        from .regional_depth_contract import verify
        verify(original, candidate, animation, partition_slots, order)
    report = dict(refinement=evidence, order=order, partition=partition,
        depth_groups=depth.get('groups'), depth_profile=depth['profile'],
        cloth_constraints=cloth, limb_constraints=limbs)
    if include_depth:
        report['depth'] = refined
    return candidate, report
