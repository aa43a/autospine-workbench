from copy import deepcopy
import unittest
import json

from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_overlap_ownership import inspect, triangle_groups


class OwnershipTests(unittest.TestCase):
    def test_straddle_report_locates_actual_overlap_without_reordering(self):
        from autospine_workbench.targets.character43.depth_ownership_review import build, render
        doc, files = fixture()
        doc['animations']['external-motion'] = doc['animations'].pop('test')
        sample = dict(tick=0,source_tick=100000,min_depth_ratio=-.1,max_depth_ratio=.2)
        depth = dict(pairs=[dict(arm_slot='a',torso_slot='b',samples=[sample])],
            order=dict(failures=[dict(reason_code='visible_depth_straddle',time=0,pair=['a','b'],
                                     overlap=dict(time=0,overlap_pixels=1)),
                                 dict(time=1,reason_code='visible_unmapped_order_conflict',conflict={'edges':[]})]))
        files.update({'skeleton.json':json.dumps(doc).encode(), 'motion-depth.json':json.dumps(depth).encode()})
        before=deepcopy(files)
        report=build(files)
        self.assertEqual(report['failure_kind'],'visible_depth_straddle')
        self.assertEqual(report['source_depth_samples'],[sample])
        self.assertGreater(report['samples'][0]['overlap_pixels'],0)
        self.assertFalse(report['selected'])
        self.assertEqual(files,before)
        self.assertIn('同一手臂跨越躯干前后',render(report).decode())

    def test_known_chest_and_unmapped_helper_are_distinct(self):
        doc, files = fixture(); doc['bones'][0]['name'] = 'chest'
        for s in doc['slots']: s['bone'] = 'chest'
        helper = dict(name='cloth', parent='chest', x=0, y=0, rotation=0)
        doc['bones'].append(helper)
        att = doc['skins'][0]['attachments']['b']['b']
        att['vertices'] = list(att['vertices'])
        for i in range(1, len(att['vertices']), 5): att['vertices'][i] = 1
        original = deepcopy(doc)
        result = inspect(Probe(doc, files, 'test'), 'a', 'b', 0)
        self.assertEqual(result['slots']['a']['groups'][0]['group'], 'chest')
        self.assertFalse(result['slots']['a']['missing_depth_evidence'])
        self.assertEqual(result['slots']['b']['groups'][0]['group'], 'unmapped')
        self.assertTrue(result['slots']['b']['missing_depth_evidence'])
        self.assertEqual(doc, original)

    def test_mixed_triangle_and_transparent_pixels_are_not_known(self):
        doc, files = fixture(True); doc['bones'][0]['name'] = 'chest'
        doc['bones'].append(dict(name='cloth', x=0, y=0, rotation=0))
        att = doc['skins'][0]['attachments']['a']['a']
        att['vertices'] = list(att['vertices']); att['vertices'][1] = 1
        groups, _ = triangle_groups(doc, att)
        self.assertEqual(groups['mixed'], [0, 1])
        self.assertEqual(inspect(Probe(doc, files, 'test'), 'a', 'b', 0)['slots'], {})

    def test_diagnostic_budget_is_enforced(self):
        doc, files = fixture()
        with self.assertRaisesRegex(ValueError, 'pixel_budget'):
            inspect(Probe(doc, files, 'test', pixel_budget=9), 'a', 'b', 0)

    def test_report_handles_historical_missing_witness_and_escapes_names(self):
        from autospine_workbench.targets.character43.depth_ownership_review import build, render
        doc, files = fixture()
        files.update({'skeleton.json': json.dumps(doc).encode(),
                      'motion-depth.json': b'{"pairs": []}'})
        report = build(files)
        self.assertEqual(report['status'], 'conflict_witness_unavailable')
        report['samples'] = [dict(time=0, pair=['<script>', 'b'], status='unmeasured', reason_code='<bad>')]
        html = render(report).decode()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
