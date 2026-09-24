"""Compile authored view correspondence to an interval-scoped Spine attachment."""
import re

from ...resolved_project import canonical_sha256
from .pose_attachment_variant import compile_variant
from .pose_geometry_patch import compile_patch
from .view_correspondence import compile_mapping


def build(document, request):
    fields = {'document_sha256', 'slot', 'animation', 'interval',
              'texture_sha256', 'texture_size', 'poses'}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError('view_pose_request_invalid')
    if request['document_sha256'] != canonical_sha256(document):
        raise ValueError('view_pose_document_changed')
    digest, size = request['texture_sha256'], request['texture_size']
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('view_pose_texture_identity_invalid')
    if (not isinstance(size, list) or len(size) != 2 or
            any(type(v) is not int or not 1 <= v <= 8192 for v in size)):
        raise ValueError('view_pose_texture_size_invalid')
    poses = request['poses']
    if not isinstance(poses, list) or not 1 <= len(poses) <= 512:
        raise ValueError('view_pose_poses_invalid')
    slot, animation = request['slot'], request['animation']
    mesh = document['skins'][0]['attachments'][slot][slot]
    mapped, uv, identities = [], None, []
    for pose in poses:
        if not isinstance(pose, dict) or set(pose) != {'time', 'correspondence'}:
            raise ValueError('view_pose_pose_invalid')
        result = compile_mapping(mesh, pose['correspondence'])
        if uv is not None and any(abs(a-b) > 1e-10 for a, b in zip(uv, result['uvs'])):
            raise ValueError('view_pose_animated_uv_requires_separate_variant')
        uv = result['uvs']
        identities.append(result['request_sha256'])
        mapped.append(dict(time=pose['time'], points=result['points']))
    geometry = dict(document_sha256=request['document_sha256'], mesh_sha256=canonical_sha256(mesh),
                    slot=slot, animation=animation, vertices=list(range(len(uv)//2)),
                    interval=request['interval'], poses=mapped)
    changed, geometry_report = compile_patch(document, geometry)
    target = changed['skins'][0]['attachments'][slot][slot]
    target.update(uvs=uv, path='view-'+digest, width=size[0], height=size[1])
    result, variant_report = compile_variant(document, changed, slot=slot, animation=animation,
        interval=request['interval'], source_sha256=request['document_sha256'])
    return result, dict(profile='authored-additional-view-variant-v1',
        request_sha256=canonical_sha256(request), correspondence_sha256s=identities,
        texture_sha256=digest, texture_path='view-'+digest,
        geometry=geometry_report, variant=variant_report, authority='none', selected=False,
        limitations=['texture_bytes_must_be_verified_and_packaged_by_caller',
                     'hard_switch_requires_material_and_geometry_boundary_review',
                     'runtime_and_visual_acceptance_not_performed'])
