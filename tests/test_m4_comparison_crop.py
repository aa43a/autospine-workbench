import unittest
from m4_candidate_comparison import crop_camera


class CropTests(unittest.TestCase):
    def test_world_camera_keeps_negative_coordinates(self):
        self.assertEqual(crop_camera([390,-330,80,100]),dict(left=390,bottom=-330,width=80,height=100))

    def test_nonfinite_empty_or_excessive_camera_rejected(self):
        for values in ([0,0,0,10],[0,0,20,5000],[float('nan'),0,10,10],[0,0,10]):
            with self.assertRaises(ValueError):crop_camera(values)
