"""Same-frame shape evidence; bone-affine compensation is exact only for one bone."""
import numpy as np


def shape(rest,current):
    rest=np.asarray(rest,dtype=float);current=np.asarray(current,dtype=float)
    if rest.shape!=(3,2) or current.shape!=(3,2) or not np.isfinite(rest).all() or not np.isfinite(current).all():
        raise ValueError('triangle_shape_invalid_points')
    basis=(rest[1:]-rest[0]).T
    if abs(np.linalg.det(basis))<1e-10:raise ValueError('triangle_shape_degenerate_setup')
    transform=(current[1:]-current[0]).T@np.linalg.inv(basis)
    return transform,describe(transform)


def describe(transform):
    values=np.linalg.svd(transform,compute_uv=False)
    return dict(minimum_stretch=float(values[-1]),maximum_stretch=float(values[0]),
        signed_area_ratio=float(np.linalg.det(transform)))


def build(rest,actual,raw,influences,bones,setup,current):
    actual_transform,actual_shape=shape(rest,actual)
    _,raw_shape=shape(rest,raw)
    used=sorted({index for row in influences for index,weight in row if weight>0})
    records=[];transforms={}
    for index in used:
        name=bones[index]['name']
        before=np.asarray(setup[name][:4],float).reshape(2,2)
        after=np.asarray(current[name][:4],float).reshape(2,2)
        if not np.isfinite(before).all() or not np.isfinite(after).all() or abs(np.linalg.det(before))<1e-10:
            raise ValueError('triangle_shape_invalid_bone')
        transform=after@np.linalg.inv(before);transforms[index]=transform
        records.append(dict(bone=name,**describe(transform)))
    single=(len(used)==1 and all(len([w for _,w in row if w>0])==1 and
            abs(sum(w for _,w in row)-1)<1e-6 for row in influences))
    compensated=None
    if single:
        transform=transforms[used[0]]
        if abs(np.linalg.det(transform))>1e-10:
            compensated=describe(np.linalg.inv(transform)@actual_transform)
    return dict(profile='triangle-bone-shape-evidence-v1',actual=actual_shape,without_deform=raw_shape,
        bones=records,reference_kind='single_bone_affine' if single else 'mixed_bone_proxy_only',
        bone_compensated=compensated,authority='none',selected=False,
        scope='shape_measurement_not_projection_causality_or_visual_acceptance')
