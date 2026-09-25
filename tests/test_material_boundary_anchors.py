import unittest
from m4_material_anchor_probe import boundary_anchors


class MaterialBoundaryAnchorsTests(unittest.TestCase):
    def test_shared_interior_vertex_is_not_a_boundary_anchor(self):
        mesh=[0,1,4,1,2,4,2,3,4,3,0,4]
        self.assertEqual(boundary_anchors(mesh,[4,0,2]),[0,2])
        self.assertEqual(boundary_anchors(mesh,[4]),[])

    def test_boundary_alone_does_not_grant_support(self):
        self.assertEqual(boundary_anchors([0,1,2],[]),[])
        self.assertEqual(boundary_anchors([0,1,2],[1,5]),[1])

    def test_ambiguous_topology_rejected(self):
        for mesh in ([0,1], [0,1,1], [0,1,2,1,0,3,0,1,4]):
            with self.assertRaises(ValueError):boundary_anchors(mesh,[0,1])
