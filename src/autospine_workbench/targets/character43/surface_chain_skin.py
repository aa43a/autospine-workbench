"""Rigid 3D chain frames and linear skinning with unchanged target weights."""
import numpy as np


def deform(vertices, influences, rest_heads, rotations, root):
    points = np.asarray(vertices, float); heads = np.asarray(rest_heads, float)
    turns = np.asarray(rotations, float); root = np.asarray(root, float)
    if (points.ndim != 2 or points.shape[1] != 3 or heads.ndim != 2 or heads.shape[1] != 3 or
            not len(heads) or turns.shape != (len(heads),3,3) or root.shape != (3,) or
            len(influences) != len(points) or not all(np.isfinite(x).all() for x in (points,heads,turns,root)) or
            any(not np.allclose(r@r.T,np.eye(3),atol=1e-7) or abs(np.linalg.det(r)-1)>1e-7 for r in turns)):
        raise ValueError('surface_chain_input')
    posed_heads = [root]
    for i in range(1,len(heads)):
        posed_heads.append(posed_heads[-1]+turns[i-1]@(heads[i]-heads[i-1]))
    result = []
    for p, row in zip(points,influences):
        if (not row or any(type(i) is not int or not 0<=i<len(heads) or
                           not np.isfinite(w) or w<0 for i,w in row) or
                abs(sum(w for _,w in row)-1)>1e-6):
            raise ValueError('surface_chain_weights')
        result.append(sum((w*(turns[i]@(p-heads[i])+posed_heads[i]) for i,w in row),np.zeros(3)))
    return np.asarray(result),np.asarray(posed_heads)
