import unittest
from PIL import Image
from m4_cloth_limb_coupling_probe import coverage,exposure_kind


class ClothLimbCouplingTests(unittest.TestCase):
    def test_invisible_frame_pixel_is_not_reported_as_new_exposure(self):
        self.assertEqual(exposure_kind(0,255,0),'not_visible_in_captured_frame')
        self.assertEqual(exposure_kind(255,255,0),'newly_exposed_source_covered_material')
        self.assertEqual(exposure_kind(255,0,0),'previously_visible_limb_material')

    def test_actual_alpha_not_only_mesh_bounds_controls_coverage(self):
        mesh={'uvs':[0,0,1,0,0,1],'triangles':[0,1,2]};points=[[0,0],[2,0],[0,2]]
        transparent=Image.new('RGBA',(2,2),(255,255,255,0))
        opaque=Image.new('RGBA',(2,2),(255,255,255,255))
        self.assertEqual(coverage(mesh,points,transparent,[.5,.5]),0)
        self.assertEqual(coverage(mesh,points,opaque,[.5,.5]),255)
        self.assertEqual(coverage(mesh,points,opaque,[3,3]),0)


if __name__=='__main__':unittest.main()
