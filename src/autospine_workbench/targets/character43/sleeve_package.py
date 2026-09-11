"""Lossless ownership subtraction and a separate unified Spine candidate inventory."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math

from ...asset.joints.partition_pixels import png
from ...automation.storage_io import canonical_bytes
from ..spine43.continuous_pose import world
from .sleeve_scene import compose_scene


def subtract_components(original, components):
    """Only exact source RGBA subsets may replace a whole source layer."""
    from PIL import Image
    with Image.open(BytesIO(original)) as image:
        size = image.size; pixels = image.convert('RGBA').tobytes()
    output = bytearray(pixels); claimed = set()
    for raw in components:
        with Image.open(BytesIO(raw)) as image:
            if image.size != size:
                raise ValueError('character_component_dimensions')
            selected = image.convert('RGBA').tobytes()
        for pos in range(0, len(pixels), 4):
            if not selected[pos+3]:
                continue
            if pos in claimed:
                raise ValueError('character_component_overlap')
            if selected[pos:pos+4] != pixels[pos:pos+4]:
                raise ValueError('character_component_not_source_subset')
            claimed.add(pos); output[pos+3] = 0
    residual = sum(output[p+3] > 0 for p in range(0, len(output), 4))
    return png('RGBA', size, bytes(output)), residual, size


def compose_package(base_files, components, candidate, skeleton, source_addresses, base_coverage):
    """Components carry verified export files and explicit source-layer ownership."""
    base = json.loads(base_files['skeleton.json'])
    files = dict(base_files)
    for name in ('playback.json', 'motion.json', 'qa.json', 'preview-manifest.json'):
        files.pop(name, None)  # These describe a different scene, not this composition.
    atlas = base_files['skeleton.atlas'].decode('utf-8')
    groups = {}; documents = []
    for item in components:
        doc = json.loads(item['files']['skeleton.json'])
        if len(doc['slots']) != 1:
            raise ValueError('character_component_slot_inventory')
        name = doc['slots'][0]['name']; image_name = 'images/' + name + '.png'
        if set(item['files']) != {'skeleton.json', 'skeleton.atlas', image_name}:
            raise ValueError('character_component_file_inventory')
        raw = item['files'][image_name]; text = item['files']['skeleton.atlas'].decode('utf-8')
        if text.splitlines()[0] != image_name:
            raise ValueError('character_atlas_page_mismatch')
        if image_name in files:
            raise ValueError('character_texture_collision')
        files[image_name] = files['editor/' + image_name] = raw
        atlas += '\n' + text + '\n'
        groups.setdefault(item['source_layer_id'], []).append((doc, raw)); documents.append(doc)
    replacements = []; records = []
    for source, entries in groups.items():
        residual, count, size = subtract_components(base_files['images/' + source + '.png'], [r[1] for r in entries])
        residual_id = source + '-unbound-residual' if count else None
        if residual_id:
            name = 'images/' + residual_id + '.png'
            if name in files:
                raise ValueError('character_texture_collision')
            files[name] = files['editor/' + name] = residual
            w, h = size
            atlas += f'\n{name}\nsize: {w},{h}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{residual_id}\nbounds: 0,0,{w},{h}\n'
        replacements.append(dict(source_layer_id=source, documents=[r[0] for r in entries], residual_id=residual_id))
        records.append(dict(layer_id=source, component_regions=[r[0]['slots'][0]['name'] for r in entries],
                            residual_region=residual_id, residual_visible_pixels=count,
                            status='partial' if count else 'weighted_candidate',
                            reason_codes=['residual_binding_required'] if count else ['mesh_review_required']))
    doc, owners = compose_scene(base, replacements, candidate, skeleton)
    checks = []; reference = {}; setup_error = 0
    base_setup = world(base, 0)
    for track in doc['animations']:
        whole = deepcopy(doc); whole['animations'] = {track: doc['animations'][track]}
        max_error = 0
        reference[track] = []
        isolated = []
        for donor in documents:
            value = deepcopy(donor); value['animations'] = {track: donor['animations'][track]}; isolated.append(value)
        for tick in range(129):
            actual = world(whole, tick/64)
            reference[track].append(dict(time=tick/64, vertices=actual))
            if tick == 0:
                for name in set(base_setup) - set(groups):
                    setup_error = max(setup_error, max(math.dist(a,b) for a,b in zip(base_setup[name],actual[name])))
            for donor in isolated:
                for name, points in world(donor, tick/64).items():
                    if len(points) != len(actual[name]):
                        raise ValueError('character_vertex_count_changed')
                    max_error = max(max_error, max((math.dist(a,b) for a,b in zip(points, actual[name])), default=0))
        checks.append(dict(animation=track, samples=129, max_component_error_px=max_error))
    if any(r['max_component_error_px'] > 1e-7 for r in checks):
        raise ValueError('character_composition_changed_deformation')
    if setup_error > 1e-7:
        raise ValueError('character_context_setup_changed')
    files['skeleton.json'] = files['editor/skeleton.json'] = canonical_bytes(doc)
    files['skeleton.atlas'] = atlas.encode('utf-8')
    files['numeric-reference.json'] = canonical_bytes(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),animations=reference))
    layers = deepcopy(base_coverage['layers'])
    for layer in layers:
        replacement = next((r for r in records if r['layer_id'] == layer['layer_id']), None)
        if replacement:
            layer.update(state=replacement['status'], reason_codes=replacement['reason_codes'], missing_region_ids=[],
                         regions=[dict(region_id=name,state='weighted_candidate') for name in replacement['component_regions']])
            if replacement['residual_region']:
                layer['regions'].append(dict(region_id=replacement['residual_region'],state='static_reference'))
    if {r['region_id'] for layer in layers for r in layer['regions']} != {s['name'] for s in doc['slots']}:
        raise ValueError('character_coverage_inventory_mismatch')
    manifest = dict(schema='autospine.character-sleeve-composition/v1', authority='none',
                    production_authorized=False, full_character_animation=False, target='4.3.26',
                    source_addresses=deepcopy(source_addresses), records=records, region_owners=owners, layers=layers,
                    profile='exact-sleeve-tracks-rgba-subset-v1',
                    animations=sorted(doc['animations']), status='needs_review',
                    qa=dict(component_fidelity=checks, unchanged_context_setup_error_px=setup_error, runtime_status='not_run',
                            full_character_contact_status='not_evaluated'),
                    files={name: sha256(raw).hexdigest() for name, raw in sorted(files.items())})
    files['character-manifest.json'] = canonical_bytes(manifest)
    return files
