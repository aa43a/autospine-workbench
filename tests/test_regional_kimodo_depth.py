"""Regional rendering must consume verified NPZ and declare midpoint assumptions."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
from tests.kimodo_npz_helpers import source_document, map_document
from test_depth_region_partition import source
from autospine_workbench.targets.character43.regional_depth_candidate import build


class RegionalKimodoTests(unittest.TestCase):
    def setUp(self):
        self.raw = build_npz(motion_member_bytes())
        self.source = source_document(self.raw)
        self.mapping = map_document()
        self.doc, self.files = source()
        self.depth = dict(profile='test', pairs=[dict(samples=[dict(source_tick=0)])])

    def test_partition_rebuild_keeps_npz_and_real_midpoint_sampler(self):
        original = deepcopy(self.doc)
        seen = []
        def refine(document, files, animation, depth, sampler, **kwargs):
            middle = (sampler.ticks[0] + sampler.ticks[1]) / 2
            self.assertEqual(set(sampler(middle)), {'upperarm_l','upperarm_r','forearm_l','forearm_r'})
            self.assertEqual(len(sampler.leg_segments(middle)), 4)
            seen.append(sampler.hand_observations(middle, full_hand=True))
            return depth, dict(rows=[])
        prefix = 'autospine_workbench.targets.character43.'
        with patch(prefix+'motion_depth.build', return_value=self.depth) as rebuild, \
                patch(prefix+'regional_depth_candidate.refine', side_effect=refine), \
                patch(prefix+'regional_depth_candidate.order_build', return_value=(None, dict(status='blocked'))):
            candidate, report = build(self.doc, self.files, 'test', self.depth, None, self.mapping,
                kimodo=(self.raw,self.source), partition_slots=['a'])
        self.assertIsNone(candidate)
        self.assertEqual(rebuild.call_args.kwargs['kimodo'], (self.raw,self.source))
        self.assertEqual(report['source_sampling']['interpolation'], 'linear_observed_positions')
        self.assertEqual(report['source_sampling']['identity'], seen[0]['identity'])
        self.assertEqual(self.doc, original)

    def test_corrupted_npz_rejected_before_ordering(self):
        with patch('autospine_workbench.targets.character43.regional_depth_candidate.order_build') as order:
            with self.assertRaises(ValueError):
                build(self.doc,self.files,'test',self.depth,None,self.mapping,
                      kimodo=(self.raw+b'corrupt',self.source))
            order.assert_not_called()
