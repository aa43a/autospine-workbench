"""Synthetic alpha components and samples diagnose coverage, never choose bones."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.chain_coverage import build_chain_coverage, validate_chain_coverage
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_layer_binding import fixture as binding_fixture


def fixture(image, box):
    candidate, assisted, _ = binding_fixture('handwear')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    raw = buffer.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    row = candidate['layers'][1]
    row.update(bbox=box, image_sha256=digest, image={'sha256': digest, 'byte_size': len(raw)})
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
    skeleton = build_reviewed_skeleton(candidate, assisted)
    bindings = build_layer_bindings(candidate, assisted, skeleton)
    return candidate, assisted, skeleton, bindings, {row['layer_id']: raw}


class ChainCoverageTests(unittest.TestCase):
    def test_four_connectivity_threshold_and_canvas_offset(self):
        from PIL import Image
        image = Image.new('RGBA', (4, 4))
        image.putpixel((0, 0), (0, 0, 0, 8))
        image.putpixel((1, 1), (0, 0, 0, 255))
        image.putpixel((2, 2), (0, 0, 0, 7))
        args = fixture(image, [10, 20, 14, 24])
        before = deepcopy(args)
        report = build_chain_coverage(*args)
        self.assertEqual(args, before)
        self.assertEqual(validate_chain_coverage(*args, report), report)
        row = report['layers'][0]
        self.assertEqual(row['alpha_pixel_count'], 2)
        self.assertEqual(row['component_count'], 2)
        self.assertEqual(row['components'][0]['bbox'], [10, 20, 11, 21])
        self.assertEqual(row['components'][1]['centroid'], [11, 21])
        self.assertEqual(len(row['options']), 3)
        self.assertTrue(all(b['sample_count'] == 21 for o in row['options'] for b in o['bones']))
        fractional = Image.new('RGBA', (2, 1), (0, 0, 0, 8))
        component = build_chain_coverage(*fixture(fractional, [10, 20, 12, 21]))['layers'][0]['components'][0]
        self.assertEqual(component['centroid'], [10.5, 20])

    def test_bilateral_disconnected_components_and_actual_bone_samples(self):
        from PIL import Image, ImageDraw
        source = binding_fixture('handwear')[2]
        image = Image.new('RGBA', (200, 400))
        draw = ImageDraw.Draw(image)
        for bone in source['bones']:
            if bone['id'].startswith(('upperarm_', 'forearm_', 'hand_')):
                draw.line([tuple(bone['head_xy']), tuple(bone['tail_xy'])], fill=(0, 0, 0, 255), width=7)
        report = build_chain_coverage(*fixture(image, [0, 0, 200, 400]))
        row = report['layers'][0]
        self.assertEqual(row['component_count'], 2)
        self.assertIn('multiple_components', row['reason_codes'])
        self.assertTrue(all(b['coverage_ratio'] == 1 for o in row['options'] for b in o['bones']))
        self.assertNotIn('suggested_option_id', row)

    def test_omission_accounting_and_no_alpha(self):
        from PIL import Image
        image = Image.new('RGBA', (20, 10))
        for i in range(40):
            image.putpixel(((i%10)*2, (i//10)*2), (0, 0, 0, 255))
        row = build_chain_coverage(*fixture(image, [10, 20, 30, 30]))['layers'][0]
        self.assertEqual(row['component_count'], 40)
        self.assertEqual(len(row['components']), 32)
        self.assertEqual(row['omitted_component_count'], 8)
        self.assertEqual(row['omitted_alpha_pixel_count'], 8)
        self.assertEqual(row['alpha_pixel_count'], sum(c['area'] for c in row['components'])+8)
        image = Image.new('RGBA', (4, 4))
        row = build_chain_coverage(*fixture(image, [10, 20, 14, 24]))['layers'][0]
        self.assertEqual(row['alpha_pixel_count'], 0)
        self.assertIn('no_alpha', row['reason_codes'])
        self.assertTrue(all('low_bone_alpha_coverage' in o['reason_codes'] for o in row['options']))

    def test_hash_size_dimensions_limits_and_output_tamper(self):
        from PIL import Image
        args = fixture(Image.new('RGBA', (4, 4), (0, 0, 0, 255)), [10, 20, 14, 24])
        images = dict(args[4]); images['layer-001'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            build_chain_coverage(*args[:4], images)
        with patch('autospine_workbench.asset.joints.chain_coverage.MAX_RUNS', 1):
            with self.assertRaisesRegex(ValueError, 'resource_limit'):
                build_chain_coverage(*args)
        mismatched = fixture(Image.new('RGBA', (4, 4)), [10, 20, 15, 24])
        with self.assertRaisesRegex(ValueError, 'dimensions_mismatch'):
            build_chain_coverage(*mismatched)
        report = build_chain_coverage(*args)
        report['layers'][0]['alpha_pixel_count'] += 1
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_chain_coverage(*args, report)


if __name__ == '__main__':
    unittest.main()
