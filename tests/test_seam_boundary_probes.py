from copy import deepcopy
import unittest
from unittest.mock import patch
from autospine_workbench.benchmark.seam_boundary_probes import build
from autospine_workbench.targets.spine43.seam_admission import evaluate
from tests import test_seam_admission


class BoundaryProbeTests(unittest.TestCase):
    def fixture(self):
        doc = {'animations': {'test': {'bones': {'bone': {'rotate': [{'time': 0}, {'time': 2}]}}}}}
        samples = [dict(triangle=[i, i, i], barycentric=[1, 0, 0]) for i in range(5)]
        alpha = dict(boundaries={n: dict(samples=samples) for n in ('a', 'b')},
                     relations=[dict(driver='a', follower='b', pairs=[dict(driver_sample=i, follower_sample=i) for i in range(5)])])
        return doc, alpha

    def test_reference_only_selection_and_full_clip(self):
        doc, alpha = self.fixture()
        original = deepcopy(alpha)
        with patch('autospine_workbench.benchmark.seam_boundary_probes.world',
                   side_effect=lambda _, t: {n: [[i+t, -i] for i in range(5)] for n in ('a', 'b')}):
            result = build(doc, alpha, 'b')
            self.assertEqual(result, build(doc, alpha, 'b'))
        row = result['relations'][0]
        self.assertEqual(row['selected_pair_indices'], [0, 2, 4])
        self.assertEqual(len(row['samples']), 183)
        self.assertEqual({s['frame'] for s in row['samples']}, set(range(61)))
        self.assertEqual(row['samples'][1]['world_point'], [2.5, -1.5])
        self.assertEqual(alpha, original)

    def test_missing_relation_and_wrong_duration_rejected(self):
        doc, alpha = self.fixture()
        with self.assertRaisesRegex(ValueError, 'relation'):
            build(doc, alpha, 'missing')
        doc['animations']['test']['bones']['bone']['rotate'][-1]['time'] = 3
        with self.assertRaisesRegex(ValueError, 'duration'):
            build(doc, alpha, 'b')

    def test_new_probe_scope_does_not_relabel_old_evidence(self):
        args = test_seam_admission.AdmissionTests().fixture()
        args[1]['schema'] = 'autospine.seam-local-runtime/v3'
        with self.assertRaisesRegex(ValueError, 'probe_schema'):
            evaluate(*args)
        args[0]['schema'] = 'autospine.seam-boundary-probes/v1'
        result = evaluate(*args)
        self.assertEqual(result['schema'], 'autospine.seam-boundary-comparison/v1')
        self.assertEqual(result['coverage'], 'reference_boundary_representative_points_only')
        self.assertEqual(result['relations'][0]['status'], 'review_runtime_alpha_loss')
        self.assertFalse(result['production_authorized'])
