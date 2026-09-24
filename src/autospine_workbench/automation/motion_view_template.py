"""Download an exact source correspondence template, never an authored pose."""
from io import BytesIO
import json
from zipfile import ZipFile

from ..resolved_project import canonical_sha256
from ..targets.character43.affine_pose import sample
from ..targets.character43.pose_geometry_patch import _times
from ..targets.character43.view_pose_variant import source_mesh
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes


def download(manager, job, revision):
    from .motion_repair_material import download as material
    from .motion_target_jobs import context
    with manager._lock:
        with ZipFile(BytesIO(material(manager, job, revision, include_preview=False))) as archive:
            request = json.loads(archive.read('request.json'))
        if not request.get('view_needs'):
            raise PipelineRunError('motion_view_template_requires_view_task')
        result, files = context(manager, job)
        if result['artifact_sha256'] != request['artifact_sha256']:
            raise PipelineRunError('motion_view_candidate_changed')
        doc = json.loads(files['skeleton.json']); slot = request['slot']; name = request['animation']
        mesh = source_mesh(doc, slot, name)
        duration = max(_times(doc['animations'][name]), default=0)
        points = sample(doc, name, request['event']['time'])[0][slot]
        source = [mesh['uvs'][i:i+2] for i in range(0, len(mesh['uvs']), 2)]
        controls = dict(mesh_sha256=canonical_sha256(mesh), source_uv=source, target_uv=source,
                        target_xy=points, triangles=[mesh['triangles'][i:i+3] for i in range(0, len(mesh['triangles']), 3)])
        pose = dict(document_sha256=canonical_sha256(doc), slot=slot, animation=name,
                    interval=[0, duration], texture_sha256=None, texture_size=None, poses=[])
        return canonical_bytes(dict(request=request, view_pose=pose, control_template=controls,
            instructions=['control_template contains source coordinates, not corrected artwork or geometry',
                          'author target_uv and target_xy, then add poses with time and correspondence',
                          'pose times must be strictly inside interval; PNG identity is filled from selected file'],
            authority='none', selected=False))
