"""Clothing proxy thresholds reject deep overlap without declaring joint truth."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.benchmark.contact_probe import build_contact_probe
from autospine_workbench.benchmark.contact_screen import build_contact_screen, validate_contact_screen
from tests.test_benchmark_contact_probe import inputs


def fixture():
    candidate, images = inputs(names=('bottomwear', 'legwear'), boxes=((10, 10, 20, 20), (14, 10, 24, 90)))
    probe = build_contact_probe(candidate, images)
    return candidate, probe


def contact(probe):
    return probe['relations'][1]['pairs'][0]['contacts'][0]


class ContactScreenTests(unittest.TestCase):
    def test_local_not_authorized_and_exact_replay(self):
        candidate, probe = fixture()
        before = deepcopy(probe)
        doc = build_contact_screen(candidate, probe)
        self.assertEqual(validate_contact_screen(candidate, probe, doc), doc)
        self.assertEqual(probe, before)
        self.assertEqual(doc['summary']['local_contact_candidate'], 1)
        self.assertTrue(doc['diagnostic_only'])
        self.assertEqual(doc['authority'], 'none')
        self.assertIsNone(doc['relations'][1]['pairs'][0]['contacts'][0]['joint_id'])

    def test_inclusive_overlap_and_height_thresholds(self):
        for overlap, height, expected in ((.099, 15, 'local_contact_candidate'),
                                          (.1, 15, 'review_required'), (.249, 15, 'review_required'),
                                          (.25, 15, 'rejected_deep_overlap'),
                                          (.01, 16, 'review_required'), (.01, 28, 'rejected_deep_overlap')):
            candidate, probe = fixture()
            row = contact(probe)
            row['overlap_ratios'][1] = overlap
            row['bbox_xywh'][3] = height
            self.assertEqual(build_contact_screen(candidate, probe)['summary'][expected], 1)

    def test_multiple_regions_keep_all_and_deep_rejection_has_priority(self):
        candidate, probe = fixture()
        second = deepcopy(contact(probe))
        second['contact_id'] += ':second'
        second['overlap_ratios'][1] = .3
        probe['relations'][1]['pairs'][0]['contacts'].append(second)
        doc = build_contact_screen(candidate, probe)
        self.assertEqual(doc['summary'], {'total': 2, 'local_contact_candidate': 0,
                                         'review_required': 1, 'rejected_deep_overlap': 1})
        for row in doc['relations'][1]['pairs'][0]['contacts']:
            self.assertIn('multiple_contact_regions', row['reason_codes'])

    def test_gap_and_uncalibrated_relations_require_review(self):
        candidate, probe = fixture()
        contact(probe).update(mode='gap', gap_distance_px=1)
        self.assertEqual(build_contact_screen(candidate, probe)['summary']['review_required'], 1)
        candidate, images = inputs()
        doc = build_contact_screen(candidate, build_contact_probe(candidate, images))
        self.assertEqual(doc['summary']['review_required'], 1)
        self.assertIn('relation_thresholds_uncalibrated', doc['relations'][0]['pairs'][0]['contacts'][0]['reason_codes'])

    def test_multiple_layer_pairs_all_require_review(self):
        candidate, images = inputs(names=('bottomwear', 'legwear-l', 'legwear-r'),
                                   boxes=((10, 10, 20, 20), (14, 10, 24, 90), (14, 10, 24, 90)))
        doc = build_contact_screen(candidate, build_contact_probe(candidate, images))
        self.assertEqual(doc['summary']['total'], 2)
        self.assertEqual(doc['summary']['review_required'], 2)
        self.assertIn('multiple_layer_pairs', doc['relations'][1]['reason_codes'])
        for pair in doc['relations'][1]['pairs']:
            self.assertIn('multiple_layer_pairs', pair['reason_codes'])
            self.assertIn('multiple_layer_pairs', pair['contacts'][0]['reason_codes'])

    def test_invalid_identity_ids_numbers_and_screen_tamper(self):
        for mutate in (lambda p: p.update(candidate_sha256='0'*64),
                       lambda p: contact(p).update(joint_id='hip.left'),
                       lambda p: contact(p).update(overlap_ratios=[0, float('nan')]),
                       lambda p: contact(p).update(overlap_ratios=[0, 10**1000]),
                       lambda p: p['relations'][1]['pairs'][0].update(layer_ids=['missing', 'layer-001'])):
            candidate, probe = fixture()
            mutate(probe)
            with self.assertRaisesRegex(ValueError, 'input_invalid'):
                build_contact_screen(candidate, probe)
        candidate, probe = fixture()
        doc = build_contact_screen(candidate, probe)
        doc['summary']['total'] = 0
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_contact_screen(candidate, probe, doc)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/benchmark-contact-screen-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(build_contact_screen(*fixture()))


if __name__ == '__main__':
    unittest.main()
