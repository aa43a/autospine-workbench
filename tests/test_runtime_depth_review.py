import unittest
from m4_runtime_depth_review import map_pixels


class RuntimeDepthReviewTests(unittest.TestCase):
    def test_world_negative_y_grid_matches_framebuffer_pixel_origins(self):
        info=dict(left=238,bottom=-1247,width=831,height=1313)
        self.assertEqual(map_pixels([[238,-66],[1068,1246]],info,(831,1313)),[(0,0),(830,1312)])

    def test_scaled_or_fractional_camera_requires_explicit_transform(self):
        info=dict(left=238,bottom=-1247,width=831,height=1313)
        with self.assertRaisesRegex(ValueError,'native_grid'):map_pixels([],info,(832,1313))
        info['left']=238.5
        with self.assertRaisesRegex(ValueError,'native_grid'):map_pixels([],info,(831,1313))

    def test_offscreen_and_fractional_diagnostic_locations_reject(self):
        info=dict(left=0,bottom=0,width=10,height=10)
        with self.assertRaisesRegex(ValueError,'pixel_bounds'):map_pixels([[10,-1]],info,(10,10))
        with self.assertRaisesRegex(ValueError,'pixel_coordinates'):map_pixels([[1.5,-1]],info,(10,10))
