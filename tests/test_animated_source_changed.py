import unittest
from types import SimpleNamespace
from unittest.mock import patch

from autospine_workbench.automation.animated_inputs import _replay, AnimatedSourceError


class SourceChangedTests(unittest.TestCase):
    def test_changed_source_is_distinct_from_invalid_artifact(self):
        store = SimpleNamespace(state_root='state', workspace_root='workspace')
        registration = dict(manifest={}, source_draft_sha256='digest')
        with patch('autospine_workbench.automation.animated_inputs.replay_inputs',
                   side_effect=ValueError('benchmark_mapping_source_changed')):
            with self.assertRaises(AnimatedSourceError) as error:
                _replay(store, registration)
            self.assertEqual(error.exception.reason_code, 'animated_source_changed')
        with patch('autospine_workbench.automation.animated_inputs.replay_inputs',
                   side_effect=ValueError('other_corruption')):
            with self.assertRaisesRegex(ValueError, 'other_corruption'):
                _replay(store, registration)
