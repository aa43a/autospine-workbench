"""Register generated artwork only on explicit knee regions; never same-canvas admission."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.registered_material_region import build


def run(source, artwork, output):
    scene = json.loads((source/'candidate.json').read_bytes())
    parent = scene['skeleton']; document = parent
    reference = json.loads((source/'active-reference.json').read_bytes())
    animation = reference['animation']; times = [f['time'] for f in reference['frames']]
    raw = artwork.read_bytes()
    with Image.open(BytesIO(raw)) as image:
        if image.format != 'PNG' or image.mode != 'RGBA':
            raise ValueError('material_probe_rgba_png_required')
        width, height = image.size
        if image.getchannel('A').getextrema()[0] != 0:
            raise ValueError('material_probe_transparency_missing')
    texture = 'experimental-knee-'+sha256(raw).hexdigest()[:12]
    source_path = parent['skins'][0]['attachments']['layer-004-cap-0']['layer-004-cap-0']['path']
    source_raw = base64.b64decode(scene['textures']['images/'+source_path+'.png'].split(',', 1)[1], validate=True)
    with Image.open(BytesIO(source_raw)) as source_image:
        source_size = list(source_image.size)
    records = []
    for slot in ('layer-004-cap-0', 'layer-004-cap-1'):
        mesh = document['skins'][0]['attachments'][slot][slot]
        selected = []
        for i in range(0, len(mesh['triangles']), 3):
            mean_v = sum(mesh['uvs'][2*v+1] for v in mesh['triangles'][i:i+3])/3
            if .32 <= mean_v <= .51:
                selected.append(i//3)
        if not selected:
            raise ValueError('material_probe_empty_region')
        plan = dict(slot=slot, animation=animation, mapping=dict(
            mesh_sha256=canonical_sha256(mesh), triangles=selected, interval=[0, max(times)],
            uv_policy='same_canvas_original_uv', geometry_policy='preserve_original_weights_and_deform',
            activation_policy='start_inclusive_end_exclusive_not_blend_or_visual_acceptance'))
        # Explicit experimental hypothesis, not an inferred or accepted alignment.
        document, report = build(document, plan, texture, [1, 0, 0, 1, 0, 0])
        records.append(report)
    if document['bones'] != parent['bones'] or document['animations'][animation]['bones'] != parent['animations'][animation]['bones']:
        raise ValueError('material_probe_motion_changed')
    scene['skeleton'] = document; scene['artifact'] = None
    scene['atlas'] += (f'\n\ntextures/{texture}.png\nsize: {width},{height}\nfilter: Linear,Linear\npma: false\nrepeat: none\n'
                       f'{texture}\nbounds: 0,0,{width},{height}\n')
    for prefix in ('textures/', 'images/', 'editor/images/'):
        scene['textures'][prefix+texture+'.png'] = 'data:image/png;base64,'+base64.b64encode(raw).decode()
    frames = []
    for time in times:
        frame = sample_active(document, animation, time)
        before = sample_active(parent, animation, time)
        for slot, points in before['vertices'].items():
            if frame['vertices'][slot] != points:
                raise ValueError('material_probe_original_geometry_changed')
        frames.append(dict(time=time, attachments=frame['attachments'], vertices=frame['vertices']))
    output.mkdir(parents=True, exist_ok=False)
    (output/'generated-knee.png').write_bytes(raw)
    report = dict(profile='generated-knee-material-probe-v1', source_sha256=canonical_sha256(parent),
                  document_sha256=canonical_sha256(document), artwork_sha256=sha256(raw).hexdigest(),
                  artwork_size=[width, height], source_size=source_size,
                  source_texture_sha256=sha256(source_raw).hexdigest(), registration=records,
                  generator='built_in_image_gen', selected=False, authority='none',
                  limitations=['not_same_canvas_return', 'normalized_identity_alignment_is_unreviewed',
                               'triangle_centroid_band_has_hard_material_boundary',
                               'inherits_key_pose_only_geometry_and_wrong_overlap_shape',
                               'new_atlas_page_has_no_padding'])
    for filename, value in [('candidate.json', scene), ('report.json', report),
                            ('active-reference.json', dict(animation=animation, frames=frames))]:
        (output/filename).write_text(json.dumps(value), encoding='utf-8')
    print(json.dumps(dict(document=report['document_sha256'], artwork=report['artwork_sha256'],
                         counts=[len(r['selected_triangles']) for r in records])))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'artwork', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args(); run(args.source, args.artwork, args.output)
