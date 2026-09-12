"""Contact tracks share material coordinates and reject corrupt references."""
from copy import deepcopy
import importlib.util
import json
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read, write
from autospine_workbench.targets.character43.skirt_candidate import generate
from autospine_workbench.targets.character43.skirt_motion_contact import analyze, locate, transport
from test_character_skirt_candidate import fixture


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class SkirtMotionContactTests(unittest.TestCase):
    def test_common_motion_cancels_and_differential_motion_is_measured(self):
        files, _ = generate(fixture(), 'a'*64, ['skirt'])
        original = deepcopy(files)
        result = analyze(files)
        self.assertEqual(files, original)
        self.assertGreater(result['rows'][0]['paired_samples'], 0)
        # Pixel centers are half a pixel below the waist and inherit a little probe sway.
        self.assertLess(result['rows'][0]['motions'][0]['peak']['separation_px'], .02)
        reference = read(files)
        frame = reference['animations']['idle'][5]
        frame['vertices']['shirt'] = [[x+3, y+4] for x, y in frame['vertices']['shirt']]
        changed = analyze(write(files, reference))
        peak = changed['rows'][0]['motions'][0]['peak']
        self.assertAlmostEqual(peak['separation_px'], 5, delta=.02)
        self.assertEqual(peak['index'], 5)
        self.assertEqual(changed['raster_crack_status'], 'not_evaluated')

    def test_missing_alpha_support_stays_unobservable(self):
        from PIL import Image
        from io import BytesIO
        files, _ = generate(fixture(), 'a'*64, ['skirt'])
        stream = BytesIO(); Image.new('RGBA', (80, 40)).save(stream, format='PNG')
        files['images/shirt.png'] = stream.getvalue()
        result = analyze(files)
        self.assertEqual(result['rows'][0]['status'], 'unobservable')
        self.assertIsNone(result['rows'][0]['motions'][0]['peak'])

    def test_material_interpolation_and_outside_rejection(self):
        points = [[0, 0], [2, 0], [0, 2]]
        anchor = locate(points, [0, 1, 2], [.5, .5])
        self.assertEqual(transport([[x+9, y-3] for x, y in points], anchor), [9.5, -2.5])
        with self.assertRaisesRegex(ValueError, 'uncovered'):
            locate(points, [0, 1, 2], [3, 3])
