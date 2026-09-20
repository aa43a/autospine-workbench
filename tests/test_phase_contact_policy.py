from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43 import phase_contact_policy as policy


class PhasePolicyTests(unittest.TestCase):
    def fixture(self, geometry=True, enabled=True):
        markers = [dict(kind='contact', limb='leg.left', start_tick=0, end_tick=1000000),
                   dict(kind='contact', limb='leg.right', start_tick=0, end_tick=1000000)]
        motion = dict(markers=[], ticks_per_second=1000000, duration_ticks=1000000)
        doc = dict(bones=[], animations={'walk': {}})
        report = dict(selected=False, status='inferred_proxy_drift', reason_codes=[],
                      before={'intervals': markers}, hypothesis=dict(markers=markers, ticks_per_second=1000000))
        source = dict(records=[dict(m, eligible=i == 0) for i, m in enumerate(markers)])
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(policy, 'stationary_select', return_value=(doc, deepcopy(report))))
        inspect_source = stack.enter_context(patch.object(policy, 'source_support', return_value=source))
        candidate = dict(doc, animations={'walk': {'bones': {}}})
        stack.enter_context(patch.object(policy, 'build', return_value=(candidate, {'rows': [dict(time=0), dict(time=1)]})))
        analyzed = stack.enter_context(patch.object(policy, 'analyze', side_effect=lambda d, n, m, t, r:
            dict(passed=True, intervals=deepcopy(m['markers']))))
        stack.enter_context(patch.object(policy, 'sample', return_value=({}, {})))
        stack.enter_context(patch.object(policy, 'inspect', return_value={'passed': geometry}))
        before = deepcopy(motion)
        output, result = policy.select(doc, 'walk', motion, [0, 1], 10, report, None, {}, enabled=enabled)
        self.assertEqual(motion, before)
        self.assertFalse(report['selected'])
        return doc, output, result, inspect_source, analyzed

    def test_partial_qualification_is_not_whole_clip_success(self):
        _, _, report, _, analyzed = self.fixture()
        self.assertTrue(report['selected'])
        self.assertEqual(report['status'], 'inferred_partial_corrected')
        self.assertEqual(len(report['phase_qualified_after']['intervals']), 1)
        self.assertEqual(len(report['after']['intervals']), 2)
        self.assertEqual(len(analyzed.call_args_list), 2)

    def test_geometry_failure_preserves_original(self):
        original, output, report, _, _ = self.fixture(geometry=False)
        self.assertIs(output, original)
        self.assertFalse(report['selected'])
        self.assertEqual(report['reason_codes'], ['phase_contact_geometry_failed'])

    def test_disabled_does_not_solve(self):
        original, output, report, inspect_source, _ = self.fixture(enabled=False)
        self.assertIs(output, original); self.assertFalse(report['selected'])
        inspect_source.assert_not_called()

    def test_source_labels_are_never_replaced(self):
        with self.assertRaisesRegex(ValueError, 'source_labels_preserved'):
            policy.select({}, 'x', {'markers': [{'kind': 'contact'}]}, [], 10, {}, None, {})
