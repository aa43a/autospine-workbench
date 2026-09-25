import unittest
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.torso_projection_candidate import point


class MaterialFrameTests(unittest.TestCase):
    def test_recovers_attachment_warp_not_just_bone_frame(self):
        reference=[(10000,20000),(10020,20000),(10000,20030),(10020,20030)]
        expected=(.7,.2,-.1,1.1,13,-22)
        current=[point(expected,*p) for p in reference]
        actual,error=fit(reference,current)
        self.assertLess(error,1e-7)
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=6)

    def test_flexible_or_reflected_material_is_not_silently_approximated(self):
        reference=[(0,0),(10,0),(0,10),(10,10)]
        for current in ([(0,0),(10,0),(0,10),(10,12)],[(0,0),(-10,0),(0,10),(-10,10)]):
            with self.assertRaises(ValueError):fit(reference,current)

    def test_collinear_material_rejected(self):
        with self.assertRaises(ValueError):fit([(0,0),(1,1),(2,2)],[(0,0),(1,1),(2,2)])


if __name__=='__main__':unittest.main()
