"""Diagnostic swing/twist decomposition, never silently discard source twist."""
import numpy as np
from .limb_surface_proxy import rotation


def decompose(turn, axis):
    turn,axis=np.asarray(turn,float),np.asarray(axis,float)
    if (turn.shape!=(3,3) or axis.shape!=(3,) or not np.isfinite(turn).all() or
            not np.isfinite(axis).all() or np.linalg.norm(axis)<1e-10 or
            not np.allclose(turn@turn.T,np.eye(3),atol=1e-7) or abs(np.linalg.det(turn)-1)>1e-7):
        raise ValueError('surface_swing_input')
    axis=axis/np.linalg.norm(axis)
    swing=rotation(axis,turn@axis);twist=swing.T@turn
    sine=float(axis@np.array([twist[2,1]-twist[1,2],twist[0,2]-twist[2,0],twist[1,0]-twist[0,1]])/2)
    cosine=float(np.clip((np.trace(twist)-1)/2,-1,1))
    return swing,dict(removed_twist_degrees=float(np.degrees(np.arctan2(sine,cosine))),
                      axis_error=float(np.linalg.norm(swing@axis-turn@axis)),
                      reconstruction_error=float(np.max(abs(swing@twist-turn))),
                      accepted=False,scope='diagnostic_source_twist_removed')
