import unittest
import numpy as np
from autospine_workbench.targets.character43.material_edge_strain import energy
from autospine_workbench.targets.character43.boundary_shape_feasible import refine


class MaterialStrainTests(unittest.TestCase):
    def test_rigid_motion_and_gradient(self):
        p=np.array([[0.,0.],[2.,0.],[0.,2.]]);edges=[[0,1],[1,2],[2,0]];lengths=[2.,np.sqrt(8),2.]
        self.assertAlmostEqual(energy(p@np.array([[0.,-1.],[1.,0.]])+5,edges,lengths)[0],0.)
        p[2]=[.3,1.1];_,gradient=energy(p,edges,lengths)
        for i in range(3):
            for j in range(2):
                a=p.copy();b=p.copy();a[i,j]+=1e-6;b[i,j]-=1e-6
                numerical=(energy(a,edges,lengths)[0]-energy(b,edges,lengths)[0])/2e-6
                self.assertAlmostEqual(gradient[i,j],numerical,places=7)

    def test_shape_objective_recovers_compression_without_relaxing_bounds(self):
        rest=[[0.,0.],[2.,0.],[0.,2.]];seed=[[0.,0.],[2.,0.],[0.,.2]]
        region=dict(vertex=2,center=[0.,1.5],inverse=[[1.,0.],[0.,1.]],radius=1.)
        before,_=refine(rest,[[0,1,2]],seed,[2],seed,seed,2,regions=[region])
        points,report=refine(rest,[[0,1,2]],seed,[2],seed,seed,2,regions=[region],shape_objective=True)
        self.assertEqual(report['status'],'feasible_candidate');self.assertGreater(points[2][1],before[2][1]+.5)
        self.assertLessEqual(report['maximum_contact_region_ratio'],1);self.assertFalse(report['geometry']['bad_triangles'])
