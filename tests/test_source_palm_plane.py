import unittest
from autospine_workbench.targets.character43.source_palm_plane import plane


class PalmPlaneTests(unittest.TestCase):
    def test_face_edge_and_reversal(self):
        front=plane([0,0,0],[1,0,0],[0,1,0])
        self.assertEqual(front['projected_area_fraction'],1)
        self.assertEqual(plane([0,0,0],[0,1,0],[1,0,0])['signed_facing'],-1)
        self.assertEqual(plane([0,0,0],[0,0,1],[0,1,0])['projected_area_fraction'],0)

    def test_translation_scale_invariant_and_degeneracy_rejected(self):
        self.assertEqual(plane([2,3,4],[4,3,4],[2,5,4]),plane([0,0,0],[1,0,0],[0,1,0]))
        with self.assertRaisesRegex(ValueError,'degenerate'):plane([0,0,0],[1,0,0],[2,0,0])
        with self.assertRaisesRegex(ValueError,'invalid'):plane([float('nan'),0,0],[1,0,0],[0,1,0])
