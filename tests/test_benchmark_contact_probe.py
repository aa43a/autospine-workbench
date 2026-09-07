"""Clothing contact measurements preserve identity and forbid joint assignment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.benchmark.contact_probe import build_contact_probe, validate_contact_probe
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png


def inputs(names=('topwear', 'handwear-l'), boxes=((10, 10, 20, 20), (14, 10, 24, 20)), alpha=255):
    layers, images = [], {}
    for i, (name, box) in enumerate(zip(names, boxes)):
        width, height = box[2]-box[0], box[3]-box[1]
        raw = encode_rgba_png(RgbaImage(width, height, bytes([0, 0, 0, alpha])*width*height))
        digest = hashlib.sha256(raw).hexdigest()
        key = f'layer-{i:03}'
        images[key] = raw
        layers.append({'layer_id': key, 'name': name, 'bbox': list(box), 'image_sha256': digest,
                       'image': {'sha256': digest, 'byte_size': len(raw)}, 'observed': {'empty': False}})
    return {'schema': 'autospine.benchmark-semantic-candidates/v1', 'authority': 'none',
            'canvas': [100, 100], 'coordinate_system': 'psd_canvas', 'layers': layers}, images


class ContactProbeTests(unittest.TestCase):
    def test_overlap_canvas_offset_and_no_joint(self):
        candidate, images = inputs()
        before = deepcopy(candidate)
        doc = build_contact_probe(candidate, images)
        self.assertEqual(doc, validate_contact_probe(candidate, images, doc))
        self.assertEqual(before, candidate)
        contact = doc['relations'][0]['pairs'][0]['contacts'][0]
        self.assertEqual(contact['area'], 60)
        self.assertEqual(contact['bbox_xywh'], [14, 10, 6, 10])
        self.assertIsNone(contact['joint_id'])
        self.assertIn('joint_assignment_blocked', contact['flags'])

    def test_gap_limit_and_strict_alpha_threshold(self):
        for x, expected in ((27, 1), (28, 0)):
            candidate, images = inputs(boxes=((10, 10, 20, 20), (x, 10, x+10, 20)))
            contacts = build_contact_probe(candidate, images)['relations'][0]['pairs'][0]['contacts']
            self.assertEqual(len(contacts), expected)
            if contacts:
                self.assertEqual(contacts[0]['gap_distance_px'], 8)
        for alpha, expected in ((8, 0), (9, 1)):
            doc = build_contact_probe(*inputs(alpha=alpha))
            self.assertEqual(len(doc['relations'][0]['pairs']), expected)

    def test_raw_names_only_missing_empty_and_outside(self):
        doc = build_contact_probe(*inputs(names=(' TOPWEAR ', 'body.arm.upper')))
        self.assertIn('missing_child_layer', doc['relations'][0]['reason_codes'])
        candidate, images = inputs(alpha=0)
        candidate['layers'][1]['observed']['empty'] = True
        self.assertIn('empty_layer_skipped', build_contact_probe(candidate, images)['relations'][0]['reason_codes'])
        candidate, images = inputs(boxes=((10, 10, 20, 20), (-1, 10, 9, 20)))
        doc = build_contact_probe(candidate, images)
        self.assertEqual(doc['relations'][0]['pairs'], [])
        self.assertIn('layer_outside_canvas_skipped', doc['relations'][0]['reason_codes'])

    def test_byte_identity_dimensions_and_tamper(self):
        candidate, images = inputs()
        images['layer-000'] += b'x'
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            build_contact_probe(candidate, images)
        candidate, images = inputs()
        candidate['layers'][0]['bbox'][2] += 1
        with self.assertRaisesRegex(ValueError, 'dimensions_mismatch'):
            build_contact_probe(candidate, images)
        candidate, images = inputs()
        doc = build_contact_probe(candidate, images)
        doc['relations'][0]['pairs'][0]['contacts'][0]['joint_id'] = 'shoulder.left'
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_contact_probe(candidate, images, doc)

    def test_resource_limit_and_schema(self):
        candidate, images = inputs()
        candidate['layers'][1]['observed']['empty'] = True
        with self.assertRaisesRegex(ValueError, 'empty_mask_mismatch'):
            build_contact_probe(candidate, images)
        with patch('autospine_workbench.benchmark.contact_probe.MAX_RUNS', 1):
            with self.assertRaisesRegex(ValueError, 'resource_limit'):
                build_contact_probe(*inputs())
        candidate, images = inputs()
        images['layer-000'] = b'invalid'
        digest = hashlib.sha256(images['layer-000']).hexdigest()
        candidate['layers'][0].update(image_sha256=digest, image={'sha256': digest, 'byte_size': 7})
        with self.assertRaisesRegex(ValueError, 'image_invalid'):
            build_contact_probe(candidate, images)
        with patch('autospine_workbench.benchmark.contact_probe.MAX_PIXELS', 100):
            with self.assertRaisesRegex(ValueError, 'resource_limit'):
                build_contact_probe(*inputs())
        with patch('autospine_workbench.benchmark.contact_probe.MAX_OUTPUT_BYTES', 100):
            with self.assertRaisesRegex(ValueError, 'output_limit'):
                build_contact_probe(*inputs())
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/benchmark-contact-probe-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(build_contact_probe(*inputs()))


if __name__ == '__main__':
    unittest.main()
