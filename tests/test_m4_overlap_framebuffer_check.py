import unittest
from m4_overlap_framebuffer_check import screen_pixel


class ScreenPixelTests(unittest.TestCase):
    def test_native_pixel_centers_and_y_flip(self):
        info=dict(left=201,bottom=-1038,width=616,height=1062)
        self.assertEqual(screen_pixel([201.5,-1037.5],info),(0,1061))
        self.assertEqual(screen_pixel([816.5,23.5],info),(615,0))
        self.assertIsNone(screen_pixel([817,0],info))
        self.assertIsNone(screen_pixel([200.999,0],info))
        self.assertIsNone(screen_pixel([202,-1038.001],info))
        self.assertIsNone(screen_pixel([202,24],info))
