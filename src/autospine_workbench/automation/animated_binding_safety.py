"""Measured bilateral layer hints; never replace or silently reinterpret a decision.

The immutable v2 choices remain readable. These display hints prevent an editor
from binding two independently placed parts to one side of a skeleton. Recovery
uses the existing pending decision, whose compiler produces independent meshes.
"""
from copy import deepcopy
import hashlib
from io import BytesIO
import math
from pathlib import Path
import unicodedata

from ..asset.joints.chain_coverage import _components, MAX_PIXELS
from ..asset.joints.layer_binding import BLOCKERS
from ..asset.joints.structure_candidates import CHAINS, PARAMETERS, assign_components
from ..project_asset_resolution import layers as layer_assets
from ..safe_input_files import read_real_file


def _name(source):
    return ' '.join(unicodedata.normalize('NFKC', source.get('name', '')).lower().split())


def bilateral_hints(candidate, skeleton, bindings, draft, images):
    """Use exactly the component/skeleton tests required by build_partitions.

    A name alone does not prove there are two shoes. One-side and ambiguous
    components keep their original options. Residual pixels remain retained.
    """
    from PIL import Image
    bones = {b['id']: b for b in skeleton['bones']}
    height = max(b['tail_xy'][1] for b in bones.values()) - min(b['head_xy'][1] for b in bones.values())
    if not math.isfinite(height) or height <= 0:
        raise ValueError('structure_height_invalid')
    decisions = {r['layer_id']: r for r in draft['records']}
    choices = {r['layer_id']: r for r in bindings['bindings']}
    result, pixels = [], 0
    for source in candidate['layers']:
        name = _name(source)
        if name not in CHAINS or source['observed']['empty'] or not source['observed']['visible']:
            continue
        if BLOCKERS.intersection(choices[source['layer_id']]['reason_codes']):
            continue
        raw = images.get(source['layer_id'])
        if type(raw) is not bytes or len(raw) > 128 << 20 or hashlib.sha256(raw).hexdigest() != source['image_sha256']:
            raise ValueError('structure_image_changed')
        x, y, right, bottom = source['bbox']
        with Image.open(BytesIO(raw)) as image:
            pixels += image.width * image.height
            if image.format != 'PNG' or image.mode != 'RGBA' or image.size != (right-x, bottom-y):
                raise ValueError('structure_image_invalid')
            if pixels > MAX_PIXELS or max(image.size) > 4096:
                raise ValueError('structure_resource_limit')
            components = _components(image.getchannel('A').tobytes(), image.width, image.height, (x, y))
        total = sum(c['area'] for c in components)
        significant = [c for c in components if c['area'] >= max(PARAMETERS['minimum_area_px'], total * PARAMETERS['minimum_area_ratio'])]
        if len(significant) != 2:
            continue
        assigned = assign_components(significant, CHAINS[name], bones, height)
        if {c['side'] for c in assigned} != {'l', 'r'}:
            continue
        decision = decisions[source['layer_id']]
        excluded = [o['id'] for o in choices[source['layer_id']]['options']
                    if o['mode'] == 'rigid' or len(o['bone_ids']) == 3]
        result.append(dict(layer_id=source['layer_id'], image_sha256=source['image_sha256'],
                           status='bilateral_partition', reason_code='bilateral_layer_requires_independent_binding',
                           current_action=decision['action'], current_option_id=decision['option_id'],
                           component_count=len(components), significant_component_count=2,
                           side_bone_ids={c['side']: deepcopy(c['bone_ids']) for c in assigned},
                           excluded_option_ids=excluded, recovery_action='pending', recovery_option_id=None,
                           residual_policy='retain_exact_rgba', method='alpha-component-structure-v1',
                           authority='none', production_authorized=False))
    return result


def partition_hints(store, project_id, info, *, selected_layer_ids=None):
    """Read current allow-listed source rasters; no project/store writes or QA grant."""
    selected = set(selected_layer_ids) if selected_layer_ids is not None else None
    choices = {r['layer_id']: r for r in info['bindings']['bindings']}
    sources = [r for r in info['candidate']['layers'] if _name(r) in CHAINS
               and not r['observed']['empty'] and r['observed']['visible']
               and not BLOCKERS.intersection(choices[r['layer_id']]['reason_codes'])
               and (selected is None or r['layer_id'] in selected)]
    if not sources:
        return []
    project_layers = {r['source_index']: r for r in store.get_project(project_id)['layers']}
    ids = [project_layers[r['traversal_index']]['id'] for r in sources]
    paths = layer_assets(store, project_id, ids)
    images = {r['layer_id']: read_real_file(Path(paths[identifier]), 128 << 20, 'project layer')
              for r, identifier in zip(sources, ids)}
    candidate = {**info['candidate'], 'layers': sources}
    return bilateral_hints(candidate, info['skeleton'], info['bindings'], info['draft'], images)


def check_binding_change(store, project_id, info, draft):
    """Reject newly selected whole-side choices for measured bilateral parts.

    Existing decisions stay inspectable and reversible. No-op saves and edits to
    unrelated layers never rewrite an old bilateral choice.
    """
    choices = {r['layer_id']: {o['id']: o for o in r['options']} for r in info['bindings']['bindings']}
    changed = []
    for before, after in zip(info['draft']['records'], draft['records']):
        if (after['action'], after['option_id']) == (before['action'], before['option_id']) or after['action'] != 'bind':
            continue
        option = choices[after['layer_id']][after['option_id']]
        if option['mode'] == 'rigid' or len(option['bone_ids']) == 3:
            changed.append(after['layer_id'])
    if partition_hints(store, project_id, info, selected_layer_ids=changed):
        from .animated_inputs import AnimatedSourceError
        raise AnimatedSourceError('animated_bilateral_binding_requires_partition')


def check_compile_binding(inputs):
    """Do not build a new single-side result from a historical bilateral choice."""
    candidates = {r['layer_id']: r for r in inputs.bindings['bindings']}
    changed = {r['layer_id'] for r in inputs.draft['records'] if r['action'] == 'bind'
               and any(o['id'] == r['option_id'] and (o['mode'] == 'rigid' or len(o['bone_ids']) == 3)
                       for o in candidates[r['layer_id']]['options'])}
    sources = [r for r in inputs.candidate['layers'] if r['layer_id'] in changed and _name(r) in CHAINS]
    if sources and bilateral_hints({**inputs.candidate, 'layers': sources}, inputs.skeleton,
                                  inputs.bindings, inputs.draft, inputs.images):
        from .animated_inputs import AnimatedSourceError
        raise AnimatedSourceError('animated_bilateral_binding_requires_partition')
