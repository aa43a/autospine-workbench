import unittest
from autospine_workbench.targets.character43.texel_coverage import covered


class TexelCoverageTests(unittest.TestCase):
    square=[[0,0],[1,0],[1,1],[0,1]]

    def test_shared_diagonal_and_duplicate_triangles(self):
        a=[[0,0],[1,0],[1,1]];b=[[0,0],[1,1],[0,1]]
        self.assertTrue(covered(self.square,[a,b]))
        self.assertFalse(covered(self.square,[a,a]))
        self.assertTrue(covered(self.square,[a,a,list(reversed(b))]))

    def test_hole_and_partial_boundary_are_not_coverage(self):
        # A corner test alone would accept this disconnected set.
        triangles=[[[0,0],[.4,0],[0,.4]],[[1,0],[.6,0],[1,.4]],
                   [[1,1],[.6,1],[1,.6]],[[0,1],[.4,1],[0,.6]]]
        self.assertFalse(covered(self.square,triangles))
        self.assertFalse(covered(self.square,[[[0,0],[.999,0],[.999,1]],[[0,0],[.999,1],[0,1]]]))

    def test_scale_translation_rotation_and_triangle_order(self):
        def transform(p):return [500-30*p[1],-200+20*p[0]]
        triangles=[[[0,0],[1,0],[1,1]],[[0,0],[1,1],[0,1]]]
        self.assertTrue(covered([transform(p) for p in self.square],
                               [[transform(p) for p in t] for t in reversed(triangles)]))

    def test_degenerate_texel_fails(self):
        self.assertFalse(covered([[0,0]]*4,[]))
