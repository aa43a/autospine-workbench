"""Whole-source context around unchanged wing candidates, without body binding authority."""
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from PIL import Image
from .wing_spine_preview import encode
from .wing_pendant_preview import setup_frames, local
from ..asset.planning.wing_edge_ownership import decode, encode as png
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import world, inspect


def build(source, files, roots, candidate, images):
    if (source.get('schema') != 'autospine.wing-pendant-preview/v1'
            or source.get('authority') != 'none' or source.get('production_authorized') is not False):
        raise ValueError('wing_context_source')
    if canonical_sha256(roots) != source['source_roots_sha256'] or len(roots['rows']) != 1:
        raise ValueError('wing_context_roots')
    if set(files) != set(source['files']) or any(sha256(files[n]).hexdigest() != d for n, d in source['files'].items()):
        raise ValueError('wing_context_files')
    relation = roots['rows'][0]
    wing_id, top_id = relation['layer_id'], relation['target_layer_id']
    layers = candidate['layers']
    ids = [r['layer_id'] for r in layers]
    if len(set(ids)) != len(ids) or not {wing_id, top_id}.issubset(ids) or set(images) != set(ids):
        raise ValueError('wing_context_layer_inventory')
    if candidate['character_id'] != roots['character_id']:
        raise ValueError('wing_context_character')
    for layer in layers:
        require_safe_token(layer['layer_id'], 'Context layer')
        raw = images[layer['layer_id']]
        if sha256(raw).hexdigest() != layer['image_sha256']:
            raise ValueError('wing_context_image_changed')
        x, y, r, b = layer['bbox']
        if decode(raw).size != (r-x, b-y):
            raise ValueError('wing_context_image_dimensions')
    before = json.loads(files['skeleton.json'])
    doc = deepcopy(before)
    if doc['skeleton']['spine'] != '4.3.26':
        raise ValueError('wing_context_target')
    bone_index = next(i for i, bone in enumerate(doc['bones']) if bone['name'] == 'chest')
    frame = setup_frames(doc['bones'])['chest']
    old_slots = {s['name']: s for s in doc['slots']}
    wing_slots = [s for s in doc['slots'] if s['name'] != 'topwear']
    outputs = dict(files)
    regions = deepcopy(source['regions'])
    atlas = files['skeleton.atlas'].decode()
    body_slots, coverage = [], []
    for layer in layers:
        name = layer['layer_id']
        if name == wing_id:
            coverage.append(dict(layer_id=name, name=layer['name'], representation='wing_candidate_parts',
                                 attachments=[s['name'] for s in wing_slots if s['name'] not in source['mounted_pendants']]))
            continue
        if name == top_id:
            body_slots.append(old_slots['topwear'])
            coverage.append(dict(layer_id=name, name=layer['name'], representation='cleaned_topwear_and_transferred_candidates',
                                 attachments=['topwear', *source['mounted_pendants']], residual_visible_pixels=source['pendant_candidates']['residual_visible_pixels']))
            continue
        attachment_id = 'context-' + name
        if attachment_id in old_slots:
            raise ValueError('wing_context_attachment_collision')
        x, y, r, b = layer['bbox']
        w, h = r-x, b-y
        points = [[x, y], [r, y], [r, b], [x, b]]
        vertices = []
        for px, py in points:
            vertices.extend([1, bone_index, *local(px, -py, frame), 1])
        doc['skins'][0]['attachments'][attachment_id] = {attachment_id: dict(
            type='mesh', path=attachment_id, uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3],
            vertices=vertices, width=w, height=h)}
        body_slots.append(dict(name=attachment_id, bone='chest', attachment=attachment_id))
        raw = images[name]
        page = Image.new('RGBA', (w+4, h+4))
        page.paste(decode(raw), (2, 2))
        texture = 'textures/' + attachment_id + '.png'
        outputs[texture] = png(page)
        outputs['editor/images/' + attachment_id + '.png'] = raw
        atlas += f'\n{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{attachment_id}\nbounds: 2,2,{w},{h}\n\n'
        regions.append(dict(id=attachment_id, setup_vertices_xy=points,
                            expected_page_uvs=[[(2+u*w)/(w+4), (2+v*h)/(h+4)] for u, v in [(0, 0), (1, 0), (1, 1), (0, 1)]],
                            source_mesh_status='rigid_context_only', review_status='unreviewed'))
        coverage.append(dict(layer_id=name, name=layer['name'], representation='rigid_context_only', attachments=[attachment_id]))
    doc['slots'] = wing_slots + body_slots
    for tick in range(121):
        old, new = world(before, tick/60), world(doc, tick/60)
        if any(old[n] != new[n] for n in old):
            raise ValueError('wing_context_existing_motion_changed')
    setup = world(doc, 0)
    for region in regions:
        for actual, expected in zip(setup[region['id']], region['setup_vertices_xy']):
            if max(abs(actual[0]-expected[0]), abs(actual[1]+expected[1])) > 1e-7:
                raise ValueError('wing_context_setup_changed')
    geometry = inspect(doc)
    if not all(r['passed'] for r in geometry['regions'].values()):
        raise ValueError('wing_context_geometry_failed')
    outputs['skeleton.json'] = encode(doc)
    editor = deepcopy(doc)
    editor['skeleton']['images'] = './images/'
    outputs['editor/skeleton.json'] = encode(editor)
    outputs['skeleton.atlas'] = atlas.encode()
    report = dict(schema='autospine.wing-character-preview/v1', profile='wing-candidates-with-rigid-source-context-v1',
                  source_pendant_sha256=canonical_sha256(source), source_candidate_sha256=canonical_sha256(candidate),
                  source_roots_sha256=canonical_sha256(roots), character_id=candidate['character_id'],
                  authority='none', production_authorized=False, status='needs_review', full_character_animation=False,
                  context_layers=coverage, context_layer_count=len(body_slots)-1,
                  draw_order='all_wing_candidates_behind_source_order_body_context',
                  body_motion='rigid_chest_context_not_reviewed_body_binding',
                  existing_attachment_motion_unchanged=True, regions=regions, geometry=geometry,
                  residual_visible_pixels=source['pendant_candidates']['residual_visible_pixels'])
    outputs['context/coverage.json'] = encode(coverage)
    outputs['README.txt'] = b'Spine 4.3.26 whole-character visual context. Body layers follow chest as rigid context only; no reviewed body bindings or production authorization. Wing candidate motion and textures unchanged. Preserved residual is not silently rendered or adopted.\n'
    rows = ''.join(f'<tr><td>{escape(r["layer_id"])}</td><td>{escape(r["name"])}</td><td>{escape(r["representation"])}</td></tr>' for r in coverage)
    outputs['review.html'] = f'''<!doctype html><meta charset="utf-8"><title>完整角色中的翼片与挂坠</title>
<style>body{{font:18px/1.7 system-ui;margin:40px;color:#243448}}td,th{{padding:8px}}</style>
<h1>完整角色上下文预览</h1><p>覆盖 {len(coverage)} 个源图层，其中 {report['context_layer_count']} 层仅作刚性身体参照。主翼、挂坠在所有身体图层后方，身体其余层保持源顺序。</p>
<p>原翼片动作保持不变，身体整体随胸部摆动以检查遮挡。这不是四肢动作合并，也不是正式身体绑定。保留 {report['residual_visible_pixels']} 个未归属像素。</p>
<p><a href="preview.zip">下载 Spine 预览</a> · <a href="context/coverage.json">逐层覆盖清单</a> · <a href="pendants/residual.png">保留残余</a></p>
<table><tr><th>图层</th><th>源名称</th><th>当前表示</th></tr>{rows}</table>'''.encode()
    report['files'] = {n: sha256(raw).hexdigest() for n, raw in outputs.items()}
    outputs['preview-manifest.json'] = encode(report)
    return report, outputs


def verify(saved, *inputs):
    if canonical_sha256(saved) != canonical_sha256(build(*inputs)[0]):
        raise ValueError('wing_context_replay')
    return deepcopy(saved)
