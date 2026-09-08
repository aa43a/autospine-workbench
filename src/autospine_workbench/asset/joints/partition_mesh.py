"""Independent regional mesh hypotheses; original partitions and residual survive."""
import hashlib
import math
from io import BytesIO

from ...alpha_grid_mesh import build_alpha_grid_mesh,AlphaGridMeshError
from ...png_rgba import decode_rgba_png
from .mesh_candidate import _grid_failure
from .joint_plane_weights import weights_for_vertices
from .mesh_weights import _rotate
from .partition_mesh_qa import evaluate,raster_support


def build_region(raw,source,side,bone_ids,skeleton):
    from PIL import Image
    row={'layer_id':source['layer_id']+'-'+side,'source_layer_id':source['layer_id'],'side':side,
         'image_sha256':hashlib.sha256(raw).hexdigest(),'bone_ids':bone_ids,'status':'blocked',
         'reason_codes':[],'vertices_xy':[],'uvs':[],'triangles':[],'weights':[],'qa':None,'raster_qa':None}
    bones={b['id']:b for b in skeleton['bones']}
    if len(bone_ids) not in (1,3) or any(not b.endswith('_'+side) or b not in bones for b in bone_ids):
        raise ValueError('partition_mesh_chain_invalid')
    chain=[bones[b] for b in bone_ids];image=decode_rgba_png(raw)
    x,y,r,b=source['bbox']
    if (image.width,image.height)!=(r-x,b-y):raise ValueError('partition_mesh_dimensions_invalid')
    try:grid=build_alpha_grid_mesh(image,grid_step_px=max(4,math.ceil(max(image.width,image.height)/32)),alpha_threshold=8)
    except AlphaGridMeshError as exc:
        row['reason_codes']=[_grid_failure(exc)];return row
    vertices=[[v[0]+x,v[1]+y] for v in grid.vertices_xy];triangles=[list(t) for t in grid.triangles]
    try:
        weights=weights_for_vertices(vertices,chain) if len(chain)==3 else [[{
            'bone_id':chain[0]['id'],'weight':1.,'local_xy':_rotate([v[k]-chain[0]['head_xy'][k] for k in (0,1)],
            -chain[0]['world_rotation_degrees'])}] for v in vertices]
    except ValueError as exc:
        if str(exc) not in ('joint_plane_degenerate','joint_plane_disconnected'):raise
        row['reason_codes']=[str(exc)];return row
    qa=evaluate(vertices,triangles,weights,chain)
    with Image.open(BytesIO(raw)) as raster:
        raster_qa=raster_support(raster.getchannel('A').tobytes(),image.width,image.height,vertices,triangles,(x,y))
    reasons=['experimental_partition_mesh','binding_not_adopted']
    if not qa['passed']:reasons.append('partition_deformation_qa_failed')
    if raster_qa['uncovered_alpha_pixels']:reasons.append('partition_raster_support_incomplete')
    row.update(vertices_xy=vertices,uvs=[list(uv) for uv in grid.uvs],triangles=triangles,weights=weights,qa=qa,
               raster_qa=raster_qa,reason_codes=reasons,status='candidate_requires_review' if len(reasons)==2 else 'blocked')
    return row
