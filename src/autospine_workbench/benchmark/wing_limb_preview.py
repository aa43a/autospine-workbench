"""Combine canonical limb candidates and rebased wings with explicit residual context."""
from copy import deepcopy
from hashlib import sha256
import json
from PIL import Image
from .wing_spine_preview import encode
from ..asset.planning.wing_edge_ownership import decode, encode as png
from ..resolved_project import canonical_sha256
from ..targets.spine43.wing_rebase import rebase
from ..targets.spine43.continuous_pose import world, inspect


def build(source, files, donor, donor_files, ownership):
    if source['schema'] != 'autospine.wing-character-preview/v1' or donor['schema'] != 'autospine.seam-stable-fallback/v1':
        raise ValueError('wing_limb_profile')
    for report, payload in [(source, files), (donor, donor_files)]:
        if report['authority'] != 'none' or report['production_authorized'] is not False:
            raise ValueError('wing_limb_authority')
        if set(report['files']) != set(payload) or any(sha256(payload[n]).hexdigest() != d for n, d in report['files'].items()):
            raise ValueError('wing_limb_files')
    base = json.loads(files['skeleton.json']); limbs = json.loads(donor_files['skeleton.json'])
    doc, rebase_error = rebase(base, limbs)
    clip = next(iter(doc['animations'].values())); limb_clip = next(iter(limbs['animations'].values()))
    duration = lambda a: max(k['time'] for t in a['bones'].values() for keys in t.values() for k in keys)
    if duration(clip) != duration(limb_clip) or duration(clip) != 2:
        raise ValueError('wing_limb_duration')
    if set(clip['bones']) & set(limb_clip['bones']):
        raise ValueError('wing_limb_track_conflict')
    clip['bones'].update(deepcopy(limb_clip['bones']))
    clip['attachments'] = deepcopy(limb_clip.get('attachments', {}))
    doc['animations'] = {'wing-limb-inspection': clip}
    parts = [p['id'] for layer in ownership['layers'] for p in layer['partitions']]
    if len(parts) != len(set(parts)) or set(parts) != set(limbs['skins'][0]['attachments']):
        raise ValueError('wing_limb_partition_inventory')
    outputs = dict(files)
    for name, raw in donor_files.items():
        if name.startswith(('textures/', 'editor/images/')):
            if name in outputs and outputs[name] != raw:
                raise ValueError('wing_limb_file_collision')
            outputs[name] = raw
    coverage = deepcopy(source['context_layers']); rows = {r['layer_id']: r for r in coverage}
    slots = {s['name']: s for s in limbs['slots']}
    replacements = {}
    for layer in ownership['layers']:
        source_id = layer['layer_id']; context_id = 'context-' + source_id
        if source_id not in rows or rows[source_id]['representation'] != 'rigid_context_only':
            raise ValueError('wing_limb_context_owner')
        names = [p['id'] for p in layer['partitions']]
        if set(names) & set(doc['skins'][0]['attachments']):
            raise ValueError('wing_limb_attachment_collision')
        page_path = 'textures/' + source_id + '.png'
        if sha256(donor_files[page_path]).hexdigest() != ownership['files'][layer['page_ref']]:
            raise ValueError('wing_limb_ownership_page')
        tile = next(t for t in layer['tiles'] if t['owner_code'] == layer['residual']['owner_code'])
        x, y, w, h = tile['rect']; page = decode(donor_files[page_path])
        residual = page.crop((x, y, x+w, y+h))
        attachment = doc['skins'][0]['attachments'][context_id][context_id]
        if (w, h) != (attachment['width'], attachment['height']):
            raise ValueError('wing_limb_residual_dimensions')
        raw = png(residual); outputs['editor/images/' + context_id + '.png'] = raw
        padded = Image.new('RGBA', (w+4, h+4)); padded.paste(residual, (2, 2))
        outputs['textures/' + context_id + '.png'] = png(padded)
        outputs['limb-residual/' + source_id + '.png'] = raw
        replacements[context_id] = [slots[n] for n in names] + [next(s for s in doc['slots'] if s['name'] == context_id)]
        rows[source_id].update(representation='limb_candidates_with_unreviewed_residual_context', attachments=names+[context_id],
                              residual_visible_pixels=layer['residual']['visible_pixels'])
        for name in names:
            doc['skins'][0]['attachments'][name] = deepcopy(limbs['skins'][0]['attachments'][name])
    doc['slots'] = [slot for old in doc['slots'] for slot in replacements.get(old['name'], [old])]
    old_slots = [s['name'] for s in doc['slots'] if s['name'] in slots]
    if old_slots != [s['name'] for s in limbs['slots']]:
        raise ValueError('wing_limb_original_order')
    for tick in range(121):
        before, after = world(limbs, tick/60), world(doc, tick/60)
        if any(before[n] != after[n] for n in before):
            raise ValueError('wing_limb_original_motion')
    geometry = inspect(doc)
    if not all(r['passed'] for r in geometry['regions'].values()):
        raise ValueError('wing_limb_geometry')
    limb_preview = json.loads(donor_files['preview-manifest.json'])
    regions = deepcopy(source['regions']) + deepcopy(limb_preview['regions'])
    for region in regions:
        if region['id'] in replacements:
            region.update(source_mesh_status='unreviewed_limb_residual_context', review_status='unreviewed')
    outputs['skeleton.json'] = encode(doc); editor = deepcopy(doc); editor['skeleton']['images'] = './images/'
    outputs['editor/skeleton.json'] = encode(editor)
    outputs['skeleton.atlas'] = files['skeleton.atlas'] + b'\n' + donor_files['skeleton.atlas']
    outputs['context/coverage.json'] = encode(coverage)
    report = dict(schema='autospine.wing-limb-preview/v1', profile='canonical-wing-and-limb-union-v1',
                  source_context_sha256=canonical_sha256(source), source_limb_sha256=canonical_sha256(donor),
                  source_ownership_sha256=canonical_sha256(ownership), source_skeleton_sha256=ownership['source_skeleton_sha256'],
                  character_id=source['character_id'], status='needs_review', authority='none', production_authorized=False,
                  full_character_animation=False, regions=regions, geometry=geometry, context_layers=coverage,
                  limb_motion_unchanged=True, wing_local_motion_max_error_px=rebase_error,
                  omitted_diagnostic_track='old_chest_sway', unresolved_wing_pixels=source['residual_visible_pixels'],
                  limb_residual_context_pixels=sum(l['residual']['visible_pixels'] for l in ownership['layers']))
    outputs['README.txt'] = b'Canonical skeleton + unchanged limb candidates + rebased wing local motion. Old diagnostic chest sway omitted. Remaining body and limb residuals are unreviewed rigid context, not approved bindings. No production authorization.\n'
    outputs['review.html'] = f'''<!doctype html><meta charset="utf-8"><title>标准骨架 · 翼片与四肢</title>
<style>body{{font:18px/1.7 system-ui;margin:40px}}</style><h1>标准骨架上的主翼、挂坠与四肢候选</h1>
<p>已合入 {len(parts)} 个四肢分区，旧四肢121帧坐标不变。旧整身胸部摆动移除，翼片局部动作保留。</p>
<p>四肢残余 {report['limb_residual_context_pixels']} 像素仅作刚性参照；翼片未归属 {report['unresolved_wing_pixels']} 像素仍独立保存。肩部、袖口和裙摆接缝尚待复核。</p>
<p><a href="preview.zip">下载 Spine 候选包</a> · <a href="context/coverage.json">覆盖清单</a></p>'''.encode()
    outputs.pop('preview-manifest.json', None)
    report['files'] = {n: sha256(raw).hexdigest() for n, raw in outputs.items()}
    outputs['preview-manifest.json'] = encode(report)
    return report, outputs


def verify(saved, *inputs):
    if canonical_sha256(saved) != canonical_sha256(build(*inputs)[0]):
        raise ValueError('wing_limb_replay')
    return deepcopy(saved)
