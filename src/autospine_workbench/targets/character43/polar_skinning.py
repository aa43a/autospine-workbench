"""Experimental pivot-anchored polar blending; no automatic adoption or QA claims."""
import math
import numpy as np

PROFILE='pivot-anchored-polar-skinning-v1-experiment'


def joint_pivot(row,bones,setup):
    if len(row)==1:return np.asarray(setup[bones[row[0][0]]['name']][4:],float)
    lookup={b['name']:b for b in bones};weighted=np.zeros(2);total=0.
    def hinge(parent,child):
        seen=set()
        while child in lookup and child not in seen:
            seen.add(child);next_name=lookup[child].get('parent')
            if next_name==parent:return child
            child=next_name
        return None
    for offset,(i,wi) in enumerate(row):
        for j,wj in row[offset+1:]:
            a,b=bones[i]['name'],bones[j]['name']
            name=hinge(a,b)or hinge(b,a)
            if name is None:raise ValueError('polar_skinning_unrelated_bones')
            weight=wi*wj;weighted+=weight*np.asarray(setup[name][4:],float);total+=weight
    return weighted/total


def solve(points,influences,bones,setup,current,*,shared_joint=False):
    points=np.asarray(points,float)
    if points.ndim!=2 or points.shape[1]!=2 or len(points)!=len(influences) or not np.isfinite(points).all():
        raise ValueError('polar_skinning_points_invalid')
    frames={}
    for index in {i for row in influences for i,w in row if w>0}:
        name=bones[index]['name'];s=np.asarray(setup[name],float);c=np.asarray(current[name],float)
        if s.shape!=(6,) or c.shape!=(6,) or not np.isfinite(s).all() or not np.isfinite(c).all():
            raise ValueError('polar_skinning_frame_invalid')
        before=s[:4].reshape(2,2);after=c[:4].reshape(2,2)
        if np.linalg.det(before)<=1e-10 or np.linalg.det(after)<=1e-10:
            raise ValueError('polar_skinning_orientation_invalid')
        affine=after@np.linalg.inv(before);translation=c[4:]-affine@s[4:]
        angle=math.atan2(affine[1,0]-affine[0,1],affine[0,0]+affine[1,1])
        cosine,sine=math.cos(angle),math.sin(angle)
        rotation=np.array([[cosine,-sine],[sine,cosine]])
        stretch=rotation.T@affine
        frames[index]=(affine,translation,s[4:],np.array([cosine,sine]),stretch)
    result=[];minimum=1.
    for point,row in zip(points,influences):
        if not row or any(not math.isfinite(w) or w<0 for _,w in row) or abs(sum(w for _,w in row)-1)>1e-6:
            raise ValueError('polar_skinning_weights_invalid')
        row=[(i,w)for i,w in row if w>0]
        pivot=joint_pivot(row,bones,setup) if shared_joint else sum(w*frames[i][2] for i,w in row)
        direction=sum(w*frames[i][3] for i,w in row)
        strength=float(np.linalg.norm(direction));minimum=min(minimum,strength)
        if strength<1e-6:raise ValueError('polar_skinning_rotation_ambiguous')
        cosine,sine=direction/strength;rotation=np.array([[cosine,-sine],[sine,cosine]])
        stretch=sum(w*frames[i][4] for i,w in row)
        anchor=sum(w*(frames[i][0]@pivot+frames[i][1])for i,w in row)
        result.append((anchor+rotation@stretch@(point-pivot)).tolist())
    return result,dict(profile='shared-joint-polar-skinning-v1-experiment' if shared_joint else PROFILE,minimum_rotation_resultant=minimum,
        authority='none',selected=False,scope='per_vertex_candidate_not_mesh_or_temporal_validation')
