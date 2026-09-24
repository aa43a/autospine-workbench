"""Read-only editor scope from an exact captured candidate and mesh triangle."""
import json
from pathlib import Path
from urllib.parse import quote

from ..resolved_project import canonical_sha256
from ..targets.character43.pose_geometry_patch import _times
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes


def read(manager, job, parts):
    from .motion_target_jobs import context, review_file
    if len(parts) != 5 or parts[0] != 'pose-geometry':
        raise PipelineRunError('pipeline_artifact_not_found')
    _, slot, animation, triangle, name = parts
    # Application assets carry no candidate data; verify identity only for data reads.
    web = Path(__file__).resolve().parents[3]/'web'
    static = {'index.html': ('pose-geometry-editor.html', 'text/html; charset=utf-8'),
              'editor.js': ('pose-geometry-editor.js', 'text/javascript'),
              'editor.css': ('pose-geometry-editor.css', 'text/css')}
    if name in static:
        filename, mime = static[name]
        return (web/filename).read_bytes(), mime
    if name in ('pose-source.js', 'motion-source-player.js'):
        return (web/'modules'/name).read_bytes(), 'text/javascript'
    if name == 'source-comparison.json':
        return review_file(manager, job, ['source-comparison.json'])
    if name in ('scene.json', 'runtime.js'):
        return review_file(manager, job, ['player-assets', name])
    if name != 'editor-config.json':
        raise PipelineRunError('pipeline_artifact_not_found')
    result, files = context(manager, job)
    document = json.loads(files['skeleton.json'])
    if not triangle.isascii() or not triangle.isdigit():
        raise ValueError('pose_editor_triangle_invalid')
    mesh = document['skins'][0]['attachments'][slot][slot]
    index = int(triangle)
    if mesh.get('type') != 'mesh' or not 0 <= index < len(mesh['triangles'])//3:
        raise ValueError('pose_editor_triangle_invalid')
    duration = max(_times(document['animations'][animation]), default=0)
    if duration <= 0:
        raise ValueError('pose_editor_duration_invalid')
    vertices = set(mesh['triangles'][3*index:3*index+3])
    seed = set(vertices)
    for start in range(0, len(mesh['triangles']), 3):
        row = mesh['triangles'][start:start+3]
        if seed.intersection(row):
            vertices.update(row)
    if name == 'editor-config.json':
        request = dict(document_sha256=canonical_sha256(document), mesh_sha256=canonical_sha256(mesh),
                       animation=animation, slot=slot, vertices=sorted(vertices), interval=[0, duration], poses=[])
        return canonical_bytes(dict(artifact=result['artifact_sha256'], request=request,
            source_comparison_url='source-comparison.json',
            execute_url='/api/motions/'+quote(job, safe='')+'/pose-geometry-execute',
            authority='none', selected=False)), 'application/json'
    raise PipelineRunError('pipeline_artifact_not_found')
