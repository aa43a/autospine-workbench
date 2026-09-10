"""Regression for nonzero canvas offsets in diagnostic image overlays."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('sleeve_diagnostic',
    Path(__file__).resolve().parents[1]/'tools/check-sleeve-unknown-coupling.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DiagnosticFrameTests(unittest.TestCase):
    def test_cropped_image_corners_share_mesh_canvas_coordinates(self):
        for box in ([235,215,463,654],[541,215,771,654],[-20,30,80,230]):
            x,y,width,height=module.image_frame(box)
            self.assertEqual([x,y,x+width,y+height],box)
        self.assertEqual(module.image_frame([541,215,771,654]),(541,215,230,439))

    def test_invalid_bounds_fail(self):
        for box in ([0,0,0,3],[0,0,3,float('nan')],[0,0,3]):
            with self.assertRaisesRegex(ValueError,'sleeve_image_bounds'):
                module.image_frame(box)
