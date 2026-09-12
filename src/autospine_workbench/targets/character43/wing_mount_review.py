"""Reuse component root analysis on exact full-character source coordinates."""
from hashlib import sha256
from html import escape
import json

from .affine_pose import sample
from .skirt_contact import source_image
from ...automation.storage_io import canonical_bytes


def build(files):
    from ...asset.planning.wing_root import analyze
    from ...asset.planning.mount_candidates import category
    document = json.loads(files['skeleton.json'])
    manifest = json.loads(files['character-manifest.json'])
    positions, bones = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    if 'chest' not in bones: raise ValueError('wing_mount_chest_missing')
    target = set(); images = []; outputs = {}; rows = []
    bounds = []
    def raster(slot):
        image, (x, y) = source_image(files, document, positions, slot)
        points = {(x+i%image.width, -y+i//image.width)
                  for i, a in enumerate(image.getchannel('A').tobytes()) if a >= 8}
        return image, (x, -y), points
    selected = [layer for layer in manifest['layers'] if layer['state'] == 'static_reference'
                and category(layer) == 'wing']
    for layer in manifest['layers']:
        torso = layer['name'] in ('topwear', 'topwear-front') and layer['state'] == 'rigid_reviewed'
        if not torso and layer not in selected: continue
        for region in layer['regions']:
            slot = region['region_id']; image, (x, y), mask = raster(slot)
            if torso: target.update(mask)
            path = document['skins'][0]['attachments'][slot][slot].get('path', slot)
            name = f'image-{len(images)}.png'; outputs[name] = files['images/'+path+'.png']
            images.append(f'<image href="{name}" x="{x}" y="{y}" width="{image.width}" height="{image.height}" opacity="{.45 if torso else 1}"/>')
            bounds.append((x, y, x+image.width, y+image.height))
    if not selected or not target: raise ValueError('wing_mount_source_missing')
    left=min(p[0] for p in bounds); top=min(p[1] for p in bounds)
    right=max(p[2] for p in bounds); bottom=max(p[3] for p in bounds)
    character_height=max(p[1] for points in positions.values() for p in points)-min(p[1] for points in positions.values() for p in points)
    anchor=[bones['chest'][0], -bones['chest'][1]]; overlays=[]; descriptions=[]
    for layer in selected:
        for region in layer['regions']:
            _, _, mask = raster(region['region_id'])
            components = analyze(mask, target, anchor, character_height)
            rows.append(dict(layer_id=layer['layer_id'], region_id=region['region_id'], components=components))
            for component in components:
                cid=component['component_id']
                descriptions.append(f'<li>{escape(layer["layer_id"])} / 区域 {cid}：{component["area_pixels"]} 像素；'
                                    f'与上衣投影重叠 {component["projected_target_coverage"]:.1%}；根部待确认。</li>')
                for index, root in enumerate(component['roots']):
                    x,y=root['source_xy']
                    overlays.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#ffcc55"/><text x="{x+6}" y="{y}" fill="white" font-size="12">{cid}:{index}</text>')
    report=dict(schema='autospine.character-wing-mount-review/v1', authority='none', selected=False,
                skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                manifest_sha256=sha256(files['character-manifest.json']).hexdigest(), rows=rows,
                coordinate_system='setup_world_x_right_y_down', proposed_parent='chest',
                limitation='projected_contact_is_not_hidden_attachment_proof')
    outputs['report.json']=canonical_bytes(report)
    outputs['index.html']=(f'<!doctype html><meta charset="utf-8"><title>翅膀根部候选</title>'
        '<style>body{background:#172330;color:white;font:17px system-ui;margin:24px}svg{width:min(95vw,1000px)}</style>'
        '<h1>翅膀与上衣：同一 Setup 坐标</h1><p>上衣半透明，翅膀使用原图。黄色点为既有算法提出的朝内根点；'
        '没有改变纹理、绑定或绘制顺序，也不推测被遮挡的根部。</p>'
        f'<svg viewBox="{left-20} {top-20} {right-left+40} {bottom-top+40}">{"".join(images+overlays)}</svg>'
        f'<ul>{"".join(descriptions)}</ul>').encode()
    return outputs
