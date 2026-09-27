import unittest
from autospine_workbench.targets.character43.joint_repair_domain import expand


class JointDomainTests(unittest.TestCase):
    def test_one_ring_releases_only_adjacent_proximal_surface(self):
        bones=[{'name':n} for n in ('calf_l','foot_l')]
        weights=[[(0,.5),(1,.5)],[(0,1)],[(1,1)],[(0,1)],[(0,1)]]
        triangles=[[0,1,2],[1,2,3]]
        free,report=expand(weights,bones,triangles,1)
        self.assertEqual(free,[True,True,False,False,False])
        self.assertEqual(report['released_vertices'],[1])
        self.assertEqual(expand(weights,bones,triangles,0)[0],[True,False,False,False,False])
        self.assertEqual(expand(weights,bones,triangles,2)[0],[True,True,False,True,False])

    def test_ignores_zero_weight_and_never_releases_unknown_owner(self):
        bones=[{'name':n} for n in ('forearm_r','hand_r','root')]
        weights=[[(0,.5),(1,.5)],[(0,1),(1,0)],[(2,1)]]
        self.assertEqual(expand(weights,bones,[[0,1,2]],1)[0],[True,True,False])

    def test_rejects_invalid_domain_and_topology(self):
        for rings in (-1,3,True):
            with self.assertRaises(ValueError):expand([],[],[],rings)
        with self.assertRaises(ValueError):expand([[(0,1)]],[{'name':'calf_l'}],[[0,1,2]],1)
