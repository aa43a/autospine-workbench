"""Experimental alpha-isoline clipping; requires isolated Shapely 2.1.2."""
import numpy as np
from shapely import Polygon, GeometryCollection, constrained_delaunay_triangles, union_all
from skimage.measure import find_contours


def clip(points,uvs,triangles,alpha):
    points=np.asarray(points,float);uv=np.asarray(uvs,float);tri=np.asarray(triangles)
    alpha=np.asarray(alpha)
    if (points.ndim!=2 or points.shape[1]!=3 or uv.shape!=(len(points),2) or alpha.ndim!=2 or
            not np.isfinite(points).all() or not np.isfinite(uv).all() or
            not np.isfinite(alpha).all() or (alpha<0).any() or (alpha>255).any()):
        raise ValueError('contour_clip_input')
    size=np.array([alpha.shape[1],alpha.shape[0]])
    shape=GeometryCollection();rings=find_contours(np.pad(alpha,1),8,fully_connected='high')
    for ring in rings:
        polygon=Polygon(ring[:,[1,0]]-.5)
        if not polygon.is_valid:raise ValueError('contour_ring_invalid')
        shape=shape.symmetric_difference(polygon)
    if shape.is_empty or not shape.is_valid:raise ValueError('contour_shape_invalid')
    pixels=uv*size;new=[];coeff=[];faces=[];lookup={};parts=[];collapsed=[]
    for ids in tri:
        source=pixels[ids];basis=np.column_stack((source[1]-source[0],source[2]-source[0]))
        if abs(np.linalg.det(basis))<1e-10:raise ValueError('contour_source_degenerate')
        part=Polygon(source).intersection(shape);parts.append(part)
        for face in constrained_delaunay_triangles(part).geoms:
            out=[]
            for xy in np.asarray(face.exterior.coords)[:3]:
                key=tuple(np.round(xy,9));ab=np.linalg.solve(basis,xy-source[0])
                weights=np.r_[1-ab.sum(),ab]
                if weights.min() < -1e-7:raise ValueError('contour_outside_source_triangle')
                weights=np.maximum(weights,0);weights/=weights.sum()
                row=np.zeros(len(points));row[ids]=weights
                if key not in lookup:
                    lookup[key]=len(new);new.append(xy);coeff.append(row)
                elif np.max(abs(np.asarray(coeff[lookup[key]])@points-row@points))>1e-6:
                    raise ValueError('contour_source_mapping_disagreement')
                out.append(lookup[key])
            if len(set(out))<3:
                if face.area>1e-10:raise ValueError('contour_weld_lost_area')
                collapsed.append(float(face.area));continue
            p=np.asarray(new)[out];cross=np.cross(np.r_[p[1]-p[0],0],np.r_[p[2]-p[0],0])[2]
            if cross<0:out.reverse()
            faces.append(out)
    if not faces:raise ValueError('contour_no_coverage')
    clipped=union_all(parts);face_area=sum(Polygon(np.asarray(new)[f]).area for f in faces)
    if abs(face_area-clipped.area)>1e-5:raise ValueError('contour_area_mismatch')
    coefficients=np.asarray(coeff)
    return dict(vertices=(coefficients@points).tolist(),uvs=(np.asarray(new)/size).tolist(),
                triangles=faces,coefficients=coefficients.tolist(),alpha_isoline=8,
                alpha_shape_area=float(shape.area),clipped_area=float(clipped.area),
                outside_source_area=float(shape.difference(clipped).area),
                contour_rings=len(rings),coordinate_weld_decimal_places=9,
                collapsed_numerical_slivers=collapsed,accepted=False)
