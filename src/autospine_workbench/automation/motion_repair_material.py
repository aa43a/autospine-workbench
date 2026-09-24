"""Export an exact, reversible intervention handoff, without synthesizing artwork."""
import base64
from hashlib import sha256
from io import BytesIO
import json
import math
import struct
from zipfile import ZipFile, ZIP_STORED, ZipInfo

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes


def _svg(points, *, image=False):
    if len(points) != 3 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise PipelineRunError('motion_material_geometry_invalid')
    xs, ys = zip(*points)
    left, top = min(xs)-10, min(ys)-10
    width, height = max(xs)-left+10, max(ys)-top+10
    coordinates = ' '.join(f'{x},{y}' for x, y in points)
    background = (f'<image href="source-texture.png" x="0" y="0" width="{image[0]}" height="{image[1]}"/>'
                  if image else '')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {top} {width} {height}">'
            f'{background}<polygon points="{coordinates}" fill="#ff334455" stroke="#ffd000" '
            'stroke-width="1" vector-effect="non-scaling-stroke"/></svg>').encode()


def build(report, row, *, preview=None):
    """The plan and full geometry report must address the identical event."""
    from .motion_repair_draft import ACTIONS
    if row.get('action') not in ACTIONS - {'withdraw'}:
        raise PipelineRunError('motion_material_plan_unavailable')
    if row['action'] != 'pose_attachment':
        raise PipelineRunError('motion_material_requires_pose_plan')
    stripped = {**report, 'rows': [{k: v for k, v in r.items() if k != 'texture'} for r in report.get('rows', [])]}
    if (row['artifact_sha256'] != report['artifact_sha256']
            or row['evidence_sha256'] != canonical_sha256(stripped)):
        raise PipelineRunError('motion_material_evidence_changed')
    matches = [r for r in report['rows'] if r['slot'] == row['slot'] and r['animation'] == row['animation']
               and row['event'] in r['details']]
    if len(matches) != 1:
        raise PipelineRunError('motion_material_event_not_found')
    texture = matches[0]['texture']
    if not texture.startswith('data:image/png;base64,'):
        raise PipelineRunError('motion_material_texture_invalid')
    try:
        raw = base64.b64decode(texture.split(',', 1)[1], validate=True)
        if len(raw) > 64 << 20 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
            raise ValueError('invalid png')
        width, height = struct.unpack('>II', raw[16:24])
        if not 0 < width <= 16384 or not 0 < height <= 16384:
            raise ValueError('invalid size')
    except (ValueError, struct.error) as exc:
        raise PipelineRunError('motion_material_texture_invalid') from exc
    event = row['event']; uv = event['texture_uv']
    if len(uv) != 3 or any(len(p) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in p) for p in uv):
        raise PipelineRunError('motion_material_uv_invalid')
    pixels = [[u*width, v*height] for u, v in uv]
    # World Y is up; SVG Y is down. Explicitly record the conversion.
    world = event['sampled_world']
    projected = [[p[0], -p[1]] for p in world]
    request = dict(schema='autospine.motion-pose-material-request/v1',
        artifact_sha256=row['artifact_sha256'], evidence_sha256=row['evidence_sha256'],
        draft_sha256=canonical_sha256(row), draft_revision=row['revision'], job_id=row['job_id'],
        slot=row['slot'], animation=row['animation'], event=event,
        texture_sha256=sha256(raw).hexdigest(), texture_size=[width,height], source_pixel_triangle=pixels,
        preview_axes='source_image_y_down; pose_svg_world_y_negated', notes=row['notes'],
        status='material_request_not_replacement', missing_art_proven=False,
        authority='none', production_authorized=False)
    from .motion_material_scope import validate as validate_views, context as view_context
    views=validate_views(row['action'],row.get('view_needs'))
    if views is not None:
        request.update(view_needs=views,return_contract='additional_view_requires_geometry_mapping')
    files = {'source-texture.png': raw, 'source-location.svg': _svg(pixels, image=(width,height)),
             'deformed-triangle.svg': _svg(projected), 'request.json': canonical_bytes(request),
             'README.txt': ('姿态素材处理任务\n\n原纹理保持原字节；source-location.svg 标出异常三角形。\n'
                 'deformed-triangle.svg 仅为失败时刻三角形形状，不是期望姿态或正确轮廓。\n'
                 '请结合工作台源动作和整角色画面判断是否需要补图，不能仅凭该形状绘制。\n'
                 '当前包不生成侧背面、不自动替换附件、不改变骨骼或验收。\n'
                 '回交素材应保持原纹理画布尺寸、透明背景和位置；需要改变画布时必须另给坐标变换。\n'
                 '在原处理草稿的“回交姿态素材”中选择本 request.json 和修改后的 RGBA PNG 保存独立版本。\n'
                 '后续仍须区域映射、构建及整段验证；保存回交不直接替换动画。\n').encode('utf-8')}
    # Keep request.json stable: existing returned artwork binds its exact hash.
    # This is additional evidence, not a new accepted geometry-edit contract.
    files['geometry-context.json'] = canonical_bytes(dict(
        schema='autospine.motion-material-geometry-context/v1',
        artifact_sha256=row['artifact_sha256'], draft_sha256=canonical_sha256(row),
        slot=row['slot'], animation=row['animation'], triangle=event['triangle'], time=event['time'],
        observed_event=event,
        current_mapping_geometry='preserve_original_weights_uv_and_deform',
        image_replacement_changes_geometry=False,
        geometric_failure_cleared_by_image_replacement=False,
        next_geometry_route='separate_geometry_or_partition_candidate_requires_validation',
        desired_geometry_provided=False, missing_art_proven=False, authority='none'))
    files['README.txt'] += (
        '\n几何限制：当前回交与区域换图保留原网格、权重、UV 和 deform。'
        '修改 PNG 不会修复三角形翻转、面积压缩或边长超限；也不能通过擦除该区域透明度清除几何失败。\n'
        'geometry-context.json 保存同一候选、时刻和三角形的原始诊断。'
        '需要改变轮廓或几何时，应另建几何/分区候选并验证；当前回交入口尚不接收新姿态网格。\n'
    ).encode('utf-8')
    if views is not None:
        files['view-needs.json']=canonical_bytes(view_context(request,views))
        files['README.txt']=(
            '新增视角素材需求\n\n本任务需要侧面、背面或弯曲关节素材及其几何对应，详见 view-needs.json。\n'
            '源图与失败姿态仅用于定位，不是期望轮廓，也不证明必须补图。\n'
            '需要提供透明素材、视角和坐标约定、源区域对应、姿态几何与使用区间。\n'
            '当前同画布 PNG 回交接口不接收此类任务；必须建立独立几何映射后再构建与验收。\n'
            '不得将侧背面图直接套用原正面 UV。此任务可由后续草稿修改或撤销，不改现有候选。\n'
        ).encode('utf-8')
    if preview is not None:
        files['pose-preview.html'] = preview
        files['README.txt'] += '\n打开 pose-preview.html 可离线播放同版本完整角色，自动定位异常三角形；它不是正确姿态或补图目标。\n'.encode('utf-8')
    files['inventory.json'] = canonical_bytes({name: sha256(value).hexdigest() for name,value in files.items()})
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, value in sorted(files.items()):
            archive.writestr(ZipInfo(name, (1980,1,1,0,0,0)), value)
    return output.getvalue()


def download(manager, job, revision, *, include_preview=True):
    from .motion_repair_draft import history
    from .motion_target_jobs import review_file
    if not revision.isascii() or not revision.isdigit() or str(int(revision)) != revision:
        raise PipelineRunError('motion_material_revision_invalid')
    report = json.loads(review_file(manager, job, ['geometry-details.json'])[0])
    with manager._lock:
        rows = history(manager, job)
        index = int(revision)-1
        if not 0 <= index < len(rows):
            raise PipelineRunError('motion_material_plan_unavailable')
        row = rows[index]
        identity = lambda r: (r['slot'], r['animation'], r['event']['triangle'], r['event']['time'])
        if any(identity(r) == identity(row) for r in rows[index+1:]):
            raise PipelineRunError('motion_material_plan_superseded')
    if not include_preview:
        return build(report, row)
    from .motion_material_preview import build as preview
    context = preview(lambda parts: review_file(manager, job, parts), row)
    return build(report, row, preview=context)
