"""Package a new-view texture and authored geometry with fresh active-mesh QA."""
import base64
from hashlib import sha256
from io import BytesIO
import json

from PIL import Image

from ...automation.motion_material_return import validate_png
from ...automation.storage_io import canonical_bytes
from .active_deformation_qa import inspect
from .active_mesh_pose import sample_active
from .numeric_reference import read, write
from .view_pose_variant import build as compile_variant

PROFILE = 'authored-additional-view-candidate-v1'


def build(files, request, png, on_progress=None):
    if not isinstance(png, bytes) or sha256(png).hexdigest() != request['texture_sha256']:
        raise ValueError('view_candidate_texture_changed')
    validate_png(base64.b64encode(png).decode('ascii'), request['texture_size'])
    document = json.loads(files['skeleton.json'])
    reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('view_candidate_reference_changed')
    name = request['animation']
    if set(reference['animations']) != {name} or set(document['animations']) != {name}:
        raise ValueError('view_candidate_single_animation_required')
    result, report = compile_variant(document, request)
    times = {r['time'] for r in reference['animations'][name]}
    times.update(r['time'] for r in report['geometry']['records'])
    duration = max(times)
    # Sample the actual float32 switch boundaries read by Spine, not just the
    # authored decimal interval; retain every original validation sample.
    for boundary in report['variant']['runtime_interval']:
        times.update(t for t in (boundary-1e-4, boundary, boundary+1e-4) if 0 <= t <= duration)
    if len(times) > 4097:
        raise ValueError('view_candidate_sample_limit')
    texture = report['texture_path']
    output = {n: raw for n, raw in files.items() if n.endswith('.png') or n == 'motion-ir.json'}
    if any(n in output for n in ('images/'+texture+'.png', 'textures/'+texture+'.png')):
        raise ValueError('view_candidate_texture_collision')
    with Image.open(BytesIO(png)) as image:
        w, h = image.size
        page = Image.new('RGBA', (w+4, h+4))
        page.paste(image, (2, 2))
        stream = BytesIO(); page.save(stream, format='PNG')
    output['images/'+texture+'.png'] = png
    output['editor/images/'+texture+'.png'] = png
    output['textures/'+texture+'.png'] = stream.getvalue()
    atlas = files['skeleton.atlas'].decode('utf-8')
    if texture in atlas.splitlines():
        raise ValueError('view_candidate_atlas_collision')
    output['skeleton.atlas'] = (atlas.rstrip()+f'\n\ntextures/{texture}.png\nsize: {w+4},{h+4}\n'
        f'filter: Linear,Linear\npma: false\nrepeat: none\n{texture}\nbounds: 2,2,{w},{h}\n').encode()
    output['skeleton.json'] = canonical_bytes(result)
    # Motion time zero can already contain bone/deform motion. Capture setup
    # separately so source-raster QA never treats that frame as the rest pose.
    setup = sample_active(dict(result, animations={'setup': {}}), 'setup', 0)
    output['rig-setup-reference.json'] = canonical_bytes(dict(
        skeleton_sha256=sha256(output['skeleton.json']).hexdigest(), time=0,
        vertices=setup['vertices'], attachments=setup['attachments']))
    frames = []
    for index, time in enumerate(sorted(times)):
        if on_progress and index % 32 == 0:
            on_progress(dict(stage='validate', index=index, total=len(times)))
        active = sample_active(result, name, time)
        frames.append(dict(time=time, attachments=active['attachments'], vertices=active['vertices']))
    reference = dict(skeleton_sha256=sha256(output['skeleton.json']).hexdigest(), animations={name: frames})
    geometry = inspect(result, reference)
    output = write(output, reference)
    parent = json.loads(files['motion-review.json'])
    contact = dict(status='not_evaluated', scope='missing_source_contact_inputs')
    if 'motion-ir.json' in files and 'motion-contact.json' in files:
        from .final_motion_contact import recheck
        contact = recheck(result, name, json.loads(files['motion-ir.json']),
                          json.loads(files['motion-contact.json']), sorted(times), parent['reference_length_px'])
    output['motion-contact.json'] = canonical_bytes(contact)
    evidence = dict(status='needs_changes', reference_length_px=parent['reference_length_px'],
        geometry_passed=geometry['passed'], runtime_status='not_evaluated',
        contact_status=contact['status'], depth_order_status='not_evaluated',
        authority='none', selected=False, production_authorized=False,
        issues=[i for i in parent.get('issues', []) if i['stage'] == 'projection'])
    for field in ('source_pose_fit', 'projected_lengths'):
        if field in parent:
            evidence[field] = parent[field]
    evidence['issues'].append(dict(stage='repair', reason_code='additional_view_requires_contact_runtime_and_visual_review'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    output.update({'deformation.json': canonical_bytes(geometry),
        'motion-review.json': canonical_bytes(evidence), 'parent-motion-review.json': files['motion-review.json'],
        'view-pose-request.json': canonical_bytes(request), 'view-pose-report.json': canonical_bytes(report),
        'motion-repair.json': canonical_bytes(dict(profile=PROFILE, slot=request['slot'], animation=name,
            geometry=geometry, sample_count=len(frames), authority='none', selected=False,
            scope='active_attachment_sampled_geometry_not_contact_or_visual_acceptance'))})
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', selected=False, production_authorized=False,
                    files={n: sha256(raw).hexdigest() for n, raw in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
