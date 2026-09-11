"""Geometry gates and reversible policy provenance on actual registration storage."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from autospine_workbench.png_rgba import RgbaImage
from autospine_workbench.automation.simple_binding_policy import _evidence
from autospine_workbench.automation.simple_binding_adoption import apply, undo, read_decision
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.automation.animated_inputs import save_binding_review, AnimatedSourceError
from tests import test_animated_binding_completion as fixtures


class FootEvidenceTests(unittest.TestCase):
    def evidence(self, bbox=None, pixels=None):
        bones={'foot_l':{'head_xy':[25,10]},'foot_r':{'head_xy':[200,10]},'calf_l':{'length':100}}
        return _evidence({'bbox':bbox or [0,0,50,50]},RgbaImage(50,50,pixels or bytes([0,0,0,255])*2500),bones,'l')

    def test_connected_compact_foreground_passes(self):
        values,checks=self.evidence()
        self.assertTrue(all(checks.values()))
        self.assertEqual(values['components'],1)

    def test_disconnected_foreground_never_auto_binds(self):
        pixels=bytearray([0,0,0,255]*2500)
        for y in range(50):pixels[(y*50+30)*4+3]=0
        values,checks=self.evidence(pixels=bytes(pixels))
        self.assertEqual(values['components'],2)
        self.assertFalse(checks['one_connected_region'])

    def test_long_calf_span_and_missing_contact_rejected(self):
        _,checks=self.evidence(bbox=[0,-60,50,-10])
        self.assertFalse(checks['no_calf_span'])
        self.assertFalse(checks['ankle_on_foreground'])


class PolicyTransactionTests(unittest.TestCase):
    setUp=fixtures.AnimatedCompletionTests.setUp

    def key(self):
        return inspect_registration(self.store,'fixture')['source_addresses']['input_identity_sha256']

    def proposal(self,source):
        rows=[]
        for record,binding in zip(source.draft['records'],source.bindings['bindings']):
            eligible=record['action']=='pending' and bool(binding['options'])
            rows.append({'layer_id':record['layer_id'],'status':'eligible' if eligible else 'preserved',
                         'option_id':binding['options'][0]['id'] if eligible else None})
        return {'rows':rows,'authority':'none'}

    def test_apply_proof_undo_and_stale_guard(self):
        before=inspect_registration(self.store,'fixture')['draft']
        # Allow a real selectable option in the transaction fixture; geometry
        # decisions are tested separately, not disguised as Runtime evidence.
        records=deepcopy(before['records'])
        records[0].update(action='pending',option_id=None)
        save_binding_review(self.store,'fixture',self.key(),records)
        with patch('autospine_workbench.automation.simple_binding_adoption.propose',self.proposal):
            result=apply(self.store,'fixture',self.key())
        self.assertTrue(result['changed'])
        doc,history=read_decision(self.store,'fixture',result['decision_sha256'])
        self.assertEqual(doc['decision_source'],'policy_auto')
        self.assertEqual(doc['after_registration_sha256'],history[-1][0])
        self.assertFalse(doc['production_authorized'])
        undo(self.store,'fixture',result['decision_sha256'],self.key())
        self.assertEqual(inspect_registration(self.store,'fixture')['draft']['records'],records)
        with self.assertRaisesRegex(AnimatedSourceError,'animated_review_conflict'):
            undo(self.store,'fixture',result['decision_sha256'],self.key())

    def test_newer_human_edit_cannot_be_undone(self):
        records=deepcopy(inspect_registration(self.store,'fixture')['draft']['records'])
        records[0].update(action='pending',option_id=None)
        save_binding_review(self.store,'fixture',self.key(),records)
        with patch('autospine_workbench.automation.simple_binding_adoption.propose',self.proposal):
            result=apply(self.store,'fixture',self.key())
        latest=deepcopy(inspect_registration(self.store,'fixture')['draft']['records'])
        latest[0]['notes']='new human review'
        save_binding_review(self.store,'fixture',self.key(),latest)
        with self.assertRaisesRegex(AnimatedSourceError,'animated_review_conflict'):
            undo(self.store,'fixture',result['decision_sha256'],self.key())
        self.assertEqual(inspect_registration(self.store,'fixture')['draft']['records'],latest)
