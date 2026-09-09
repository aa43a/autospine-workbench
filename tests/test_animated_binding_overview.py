"""Display metadata must not alter addressed binding candidates or decisions."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.animated_application import AnimatedApplication


class BindingOverviewTests(unittest.TestCase):
    def test_names_join_by_source_id_without_mutating_candidates(self):
        source = {
            'source_addresses': {'input_identity_sha256': 'b' * 64},
            'candidate': {'layers': [{'layer_id': 'layer-001', 'name': 'face'},
                                     {'layer_id': 'layer-000', 'name': 'back hair'}]},
            'bindings': {'bindings': [{'layer_id': 'layer-000', 'options': []},
                                      {'layer_id': 'layer-001', 'options': []}]},
            'draft': {'records': [{'layer_id': 'layer-000', 'action': 'pending'},
                                  {'layer_id': 'layer-001', 'action': 'bind'}]},
        }
        before = deepcopy(source)
        app = object.__new__(AnimatedApplication)
        app.projects = object()
        with patch('autospine_workbench.automation.animated_application._read',
                   return_value=(None, None, SimpleNamespace(resolved_project_sha256='a' * 64))), \
             patch('autospine_workbench.automation.animated_application.inspect_registration', return_value=source):
            result = app.overview('project')
        self.assertEqual([r['name'] for r in result['binding_review']['bindings']], ['back hair', 'face'])
        self.assertEqual(source, before)
        self.assertEqual(result['binding_review']['records'], before['draft']['records'])
        self.assertEqual(len(result['review_items']), 1)
        self.assertEqual(result['authority'], 'none')
