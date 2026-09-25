"""Sparse texture evidence at selected triangle centers, never a coverage gate."""
from collections import Counter
import numpy as np


def alpha_at(texture, uv):
    height,width=texture.shape
    x,y=np.floor(np.asarray(uv)*[width,height]).astype(int)
    return int(texture[y,x]) if 0<=x<width and 0<=y<height else 0


def inspect(points, uvs, triangles, selected, reference, reference_uvs,
            reference_triangles, source_alpha, reference_alpha):
    p=np.asarray(points,float); uv=np.asarray(uvs,float).reshape(-1,2)
    q=np.asarray(reference,float); quv=np.asarray(reference_uvs,float).reshape(-1,2)
    tri=np.asarray(triangles).reshape(-1,3); other=np.asarray(reference_triangles).reshape(-1,3)
    if len(selected)*len(other)>1000000:
        return dict(status='sampling_budget_exceeded',records=[],counts={},visual_status='not_checked')
    if not all(np.isfinite(a).all() for a in (p,uv,q,quv)):
        raise ValueError('occlusion_alpha_nonfinite')
    rows=[]
    for index in selected:
        ids=tri[index]; world=p[ids].mean(axis=0); source=alpha_at(source_alpha,uv[ids].mean(axis=0))
        row=dict(triangle=index,world=world.tolist(),source_alpha=source,reference_alpha=None)
        if abs(np.linalg.det(np.column_stack((p[ids[1]]-p[ids[0]],p[ids[2]]-p[ids[0]]))))<1e-12:
            row['classification']='degenerate_source'
        elif source<8:row['classification']='source_transparent'
        else:
            matches=[]
            for indices in other:
                a,b,c=q[indices]; matrix=np.column_stack((b-a,c-a))
                if abs(np.linalg.det(matrix))<1e-12:continue
                weights=np.linalg.solve(matrix,world-a); weights=np.array([1-weights.sum(),*weights])
                if weights.min()>=-1e-9:matches.append(weights@quv[indices])
            if any(np.linalg.norm(value-matches[0])>1e-6 for value in matches[1:]):
                row['classification']='reference_mapping_ambiguous'
            else:
                value=alpha_at(reference_alpha,matches[0]) if matches else 0
                row.update(reference_alpha=value,reference_mesh_covered=bool(matches),
                    classification='opaque_reference' if value>=254 else 'partial_reference' if value else 'exposed')
        rows.append(row)
    return dict(status='sampled',records=rows,counts=dict(Counter(r['classification'] for r in rows)),
        visual_status='not_checked',scope='one_nearest_texel_sample_per_triangle_not_pixel_area_or_framebuffer',
        selected=False,authority='none')
