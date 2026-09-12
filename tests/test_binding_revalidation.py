"""Rechecking evidence never rewrites selections or turns failed probes into approval."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from autospine_workbench.automation.binding_revalidation import revalidate


class BindingRevalidationTests(unittest.TestCase):
    def fixture(self):
        source=SimpleNamespace(source_addresses={'input_identity_sha256':'a'*64},
            draft={'records':[dict(layer_id='face',action='bind',option_id='rigid:head',notes=''),
                              dict(layer_id='manual',action='bind',option_id='rigid:head',notes='keep')]})
        rows=[dict(layer_id='face',decision_source='policy_auto',evidence_current=False,
                   decision_sha256='b'*64,option_id='rigid:head',action='bind',policy_id='reviewed-head-anchor-binding-v4'),
              dict(layer_id='manual',decision_source='explicit_selection',evidence_current=None)]
        return source,rows

    def test_fresh_probe_is_bound_to_current_input_and_preserves_originals(self):
        source,rows=self.fixture();before=deepcopy((source.draft,rows))
        def propose(probe):
            self.assertEqual(probe.draft['records'][0]['action'],'pending')
            self.assertEqual(probe.draft['records'][1],source.draft['records'][1])
            return dict(policy_id='reviewed-head-anchor-binding-v4',limits={'threshold':.9},
                rows=[dict(layer_id='face',status='eligible',option_id='rigid:head',checks={'inside':True},evidence={'ratio':1},reason_codes=[])])
        with patch('autospine_workbench.automation.binding_revalidation.propose',propose):
            result=revalidate(source,rows)
        self.assertEqual(result['source_addresses'],source.source_addresses)
        self.assertTrue(result['rows'][0]['passed'])
        self.assertEqual(result['rows'][0]['decision_sha256'],'b'*64)
        self.assertEqual((source.draft,rows),before)
        self.assertFalse(result['production_authorized'])

    def test_ineligible_or_different_option_does_not_validate(self):
        for status,option in [('needs_review',None),('eligible','rigid:neck')]:
            source,rows=self.fixture()
            with patch('autospine_workbench.automation.binding_revalidation.propose',return_value=dict(policy_id='v4',limits={},
                rows=[dict(layer_id='face',status=status,option_id=option,checks={},evidence={},reason_codes=['contact'])])):
                self.assertFalse(revalidate(source,rows)['rows'][0]['passed'])

    def test_manual_current_and_unknown_policy_are_not_reinterpreted(self):
        source,rows=self.fixture();rows[0]['policy_id']='unknown-policy'
        with patch('autospine_workbench.automation.binding_revalidation.propose') as call:
            self.assertFalse(revalidate(source,rows)['rows'][0]['passed']);call.assert_not_called()
        rows[0]['evidence_current']=True
        self.assertEqual(revalidate(source,rows)['rows'],[])

    def test_frozen_inputs_are_not_modified(self):
        from dataclasses import make_dataclass
        source,rows=self.fixture()
        frozen=make_dataclass('FrozenInputs',['draft','source_addresses'],frozen=True)(source.draft,source.source_addresses)
        with patch('autospine_workbench.automation.binding_revalidation.propose',return_value=dict(policy_id='v4',limits={},
            rows=[dict(layer_id='face',status='needs_review',option_id=None,checks={},evidence={},reason_codes=[])])):
            self.assertFalse(revalidate(frozen,rows)['rows'][0]['passed'])
        self.assertEqual(frozen.draft['records'][0]['action'],'bind')
