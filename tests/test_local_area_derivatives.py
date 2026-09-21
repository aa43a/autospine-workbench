import unittest
import numpy as np
from autospine_workbench.targets.character43.local_area_derivatives import jacobian


class DerivativeTests(unittest.TestCase):
    def test_all_inequalities_match_independent_central_difference(self):
        base=np.array([[0.,0.],[2.,.2],[.5,1.]]);tri=np.array([[0,1,2]]);edges=np.array([[0,1],[1,2],[0,2]])
        indices=np.array([1,2]);budget=.7;refs=np.array([.8]);lengths=np.array([2.,1.5,1.]);v=np.array([.1,.2,-.2,.1])
        def values(x):
            p=base.copy();p[indices]+=budget*x.reshape(2,2);a,b,c=p
            ratio=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/1.6
            return np.r_[ratio-.50001,1.99999-ratio,1.99999**2-np.sum((p[edges[:,0]]-p[edges[:,1]])**2,axis=1)/lengths**2,1-np.sum(x.reshape(2,2)**2,axis=1)]
        p=base.copy();p[indices]+=budget*v.reshape(2,2)
        numeric=np.column_stack([(values(v+e*1e-6)-values(v-e*1e-6))/2e-6 for e in np.eye(4)])
        np.testing.assert_allclose(jacobian(p,tri,refs,edges,lengths,indices,budget,v),numeric,atol=1e-8)
