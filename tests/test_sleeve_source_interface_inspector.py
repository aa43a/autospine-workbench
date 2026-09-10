import importlib.util
from pathlib import Path
import unittest
from PIL import Image


spec = importlib.util.spec_from_file_location('interface_inspector',
    Path(__file__).resolve().parents[1]/'tools/inspect-sleeve-source-interfaces.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceInterfaceInspectorTests(unittest.TestCase):
    def test_opaque_center_does_not_prove_opaque_margin(self):
        alpha = Image.new('L', (5, 5), 255)
        alpha.putpixel((1, 1), 220)
        before = alpha.tobytes()
        sample = module.sample_edge([2., 2.], [2., 2.], alpha)[0]
        self.assertEqual(sample['alpha'], 255)
        self.assertEqual(sample['margin_alpha'], 220)
        self.assertEqual(alpha.tobytes(), before)

    def test_outside_texture_is_missing_not_opaque(self):
        alpha = Image.new('L', (5, 5), 255)
        sample = module.sample_edge([-2., -2.], [-2., -2.], alpha)[0]
        self.assertIsNone(sample['alpha'])
        self.assertIsNone(sample['margin_alpha'])

    def test_source_length_sampling_and_fully_opaque_margin(self):
        alpha = Image.new('L', (8, 8), 255)
        samples = module.sample_edge([2., 2.], [5., 6.], alpha)
        self.assertEqual(len(samples), 5)
        self.assertEqual([s['u'] for s in samples], [.1, .3, .5, .7, .9])
        self.assertTrue(all(s['margin_alpha'] == 255 for s in samples))
