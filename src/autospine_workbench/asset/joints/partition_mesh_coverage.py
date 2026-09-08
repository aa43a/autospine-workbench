"""Full-alpha remeshing plus a separate, unadopted distal-transition experiment."""
from copy import deepcopy
import hashlib
import math

from ...alpha_grid_mesh import build_alpha_grid_mesh,AlphaGridMeshError
from ...png_rgba import decode_rgba_png
from ...resolved_project import canonical_sha256
from .joint_plane_weights import weights_for_vertices,_planes
from .mesh_weights import _rotate
from .mesh_candidate import _grid_failure
from .partition_mesh_qa import evaluate,raster_support


def distal_trial(vertices,chain,weights):
    """Do not blend the distal bone behind its bisector plane; retain main joint."""
    result=deepcopy(weights);pivot,normal,width=_planes(chain)[1]
    for vertex,row in zip(vertices,result):
        t=max(0.,min(1.,sum((vertex[i]-pivot[i])*normal[i] for i in (0,1))/width))
        distal=t*t*(3-2*t);downstream=row[1]['weight']+row[2]['weight']
        row[1]['weight']=downstream*(1-distal);row[2]['weight']=downstream*distal
    return result


def improve(baseline,candidate,skeleton,images,*,supported=False):
    if baseline['profile']!='partition-joint-plane-grid-v1' or baseline['source_skeleton_sha256']!=canonical_sha256(skeleton):
        raise ValueError('partition_coverage_source_mismatch')
    result=deepcopy(baseline)
    result.update(profile='partition-full-alpha-v2',source_mesh_sha256=canonical_sha256(baseline),distal_trials=[])
    if supported:result['profile']='partition-full-alpha-supported-v2'
    sources={r['layer_id']:r for r in candidate['layers']};bones={b['id']:b for b in skeleton['bones']}
    for row in result['layers']:
        source=sources[row['layer_id']];raw=images[row['layer_id']]
        if hashlib.sha256(raw).hexdigest()!=row['image_sha256']:raise ValueError('partition_coverage_image_changed')
        image=decode_rgba_png(raw);x,y,r,b=source['bbox']
        if (image.width,image.height)!=(r-x,b-y):raise ValueError('partition_coverage_dimensions_invalid')
        row.update(vertices_xy=[],uvs=[],triangles=[],weights=[],qa=None,raster_qa=None,status='blocked')
        try:
            step=max(4,math.ceil(max(image.width,image.height)/32))
            if supported:
                from .full_alpha_grid import build_supported_grid
                grid=build_supported_grid(image,step)
            else:grid=build_alpha_grid_mesh(image,grid_step_px=step,alpha_threshold=1)
        except AlphaGridMeshError as exc:
            row['reason_codes']=[_grid_failure(exc)];continue
        vertices=[[v[0]+x,v[1]+y] for v in grid.vertices_xy];triangles=[list(t) for t in grid.triangles]
        chain=[bones[i] for i in row['bone_ids']]
        try:
            weights=weights_for_vertices(vertices,chain) if len(chain)==3 else [[{'bone_id':chain[0]['id'],'weight':1.,
                'local_xy':_rotate([v[i]-chain[0]['head_xy'][i] for i in (0,1)],-chain[0]['world_rotation_degrees'])}] for v in vertices]
        except ValueError as exc:
            if str(exc) not in ('joint_plane_degenerate','joint_plane_disconnected'):raise
            row['reason_codes']=[str(exc)];continue
        qa=evaluate(vertices,triangles,weights,chain)
        coverage=raster_support(image.pixels[3::4],image.width,image.height,vertices,triangles,(x,y))
        reasons=['full_alpha_grid','binding_not_adopted']
        if not qa['passed']:reasons.append('partition_deformation_qa_failed')
        if coverage['uncovered_alpha_pixels']:reasons.append('partition_raster_support_incomplete')
        row.update(vertices_xy=vertices,uvs=[list(uv) for uv in grid.uvs],triangles=triangles,weights=weights,qa=qa,
                   raster_qa=coverage,reason_codes=reasons,status='candidate_requires_review' if len(reasons)==2 else 'blocked')
        if len(chain)==3:
            trial=distal_trial(vertices,chain,weights)
            result['distal_trials'].append({'layer_id':row['layer_id'],'profile':'distal-forward-halfwidth-v1',
                'adopted':False,'weights':trial,'qa':evaluate(vertices,triangles,trial,chain)})
    return result
