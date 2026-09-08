import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_gap_boundary import edges, probe, outside_reachable


class BoundaryTests(unittest.TestCase):
    def test_equal_distance_normals_keep_ambiguity(self):
        left=dict(a=[-.5,-1],b=[-.5,1],normal=[1,0])
        right=dict(a=[.5,-1],b=[.5,1],normal=[-1,0])
        result=probe([0,0],[[left,right],[right]])
        self.assertEqual(result['evidence'],'ambiguous_boundary_ties')
        self.assertEqual(len(result['driver_nearest']),2)

    def test_open_crack_has_opposed_facing_edges(self):
        a=np.zeros((9,9),dtype=bool);b=a.copy();a[:,:4]=True;b[:,5:]=True
        row=probe([4.5,-4.5],[edges(a,[0,0,9,9]),edges(b,[0,0,9,9])])
        self.assertEqual(row['evidence'],'opposed_facing_boundaries')
        self.assertEqual(row['driver_nearest'][0]['distance'],.5)
        self.assertIn((4,4),outside_reachable(a|b))

    def test_same_side_not_opposed(self):
        a=np.zeros((9,9),dtype=bool);a[:,:4]=True
        self.assertEqual(probe([4.5,-4.5],[edges(a,[0,0,9,9])]*2)['evidence'],'no_opposed_nearest_boundaries')

    def test_artificial_roi_border_not_boundary(self):
        self.assertEqual(edges(np.ones((3,3),dtype=bool),[0,0,3,3]),[])
        self.assertEqual(probe([0,0],[[],[]])['evidence'],'insufficient_boundary_evidence')

    def test_enclosed_hole_and_offset(self):
        a=np.ones((5,5),dtype=bool);a[2,2]=False
        self.assertNotIn((2,2),outside_reachable(a))
        boundary=edges(a,[100,200,5,5])
        self.assertEqual(len(boundary),4)
        self.assertTrue(all(e['a'][0]>=102 and e['a'][1]<=-202 for e in boundary))
