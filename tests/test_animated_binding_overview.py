"""Display metadata must not alter addressed binding candidates or decisions."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.animated_application import AnimatedApplication


class BindingOverviewTests(unittest.TestCase):
    def test_names_join_by_source_id_without_mutating_candidates(self):
        source = {
            'skeleton_status': 'candidate_requires_review',
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

    def test_unreviewed_skeleton_is_visible_before_build_and_keeps_review_access(self):
        source = dict(source_addresses={'input_identity_sha256':'b'*64},
            candidate={'layers':[]}, bindings={'bindings':[]}, draft={'records':[]},
            skeleton_status='blocked')
        app = object.__new__(AnimatedApplication); app.projects = object()
        with patch('autospine_workbench.automation.animated_application._read',
                   return_value=(None,None,SimpleNamespace(resolved_project_sha256='a'*64))), \
             patch('autospine_workbench.automation.animated_application.inspect_registration',return_value=source):
            result=app.overview('project')
            self.assertFalse(result['can_build'])
            self.assertEqual(result['reason_code'],'joint_review_required')
            self.assertEqual(result['review_items'][0]['type'],'joint')
            self.assertEqual(result['input_identity_sha256'],'b'*64)
            source['skeleton_status']='candidate_requires_review'
            self.assertTrue(app.overview('project')['can_build'])

    def test_unreviewed_bilateral_layers_do_not_load_rasters_or_hide_joint_review(self):
        source = dict(source_addresses={'input_identity_sha256': 'b'*64},
            candidate={'layers': [dict(layer_id=f'layer-{i:03}', name=name,
                                      observed={'empty': False, 'visible': True})
                                  for i, name in enumerate(('legwear', 'footwear'))]},
            bindings={'bindings': [dict(layer_id=f'layer-{i:03}', options=[],
                                        reason_codes=['skeleton_blocked']) for i in range(2)]},
            draft={'records': [dict(layer_id=f'layer-{i:03}', action='pending', option_id=None)
                               for i in range(2)]},
            skeleton={'bones': []}, skeleton_status='blocked')
        before = deepcopy(source)
        app = object.__new__(AnimatedApplication); app.projects = object()
        with patch('autospine_workbench.automation.animated_application._read',
                   return_value=(None, None, SimpleNamespace(resolved_project_sha256='a'*64))), \
             patch('autospine_workbench.automation.animated_application.inspect_registration', return_value=source), \
             patch('autospine_workbench.automation.animated_binding_safety.layer_assets') as assets, \
             patch('autospine_workbench.automation.animated_binding_safety.read_real_file') as read:
            result = app.overview('project')
        assets.assert_not_called(); read.assert_not_called()
        self.assertEqual(result['binding_review']['partition_hints'], [])
        self.assertFalse(result['can_build'])
        self.assertEqual(result['reason_code'], 'joint_review_required')
        self.assertEqual(result['review_items'][0]['type'], 'joint')
        self.assertEqual(source, before)
