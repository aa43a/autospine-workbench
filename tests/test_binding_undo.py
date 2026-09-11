"""Batch undo merges untouched decisions and refuses later edits to that batch."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from autospine_workbench.automation.binding_undo import plan_undo


class BindingUndoTests(unittest.TestCase):
    def fixture(self,changes):
        row=lambda key,action='pending':dict(layer_id=key,action=action,option_id='rigid:head' if action=='bind' else None,notes='')
        before={'source_bindings_sha256':'same','records':[row('head'),row('shoe'),row('human')]}
        after=deepcopy(before);after['records'][0]=row('head','bind')
        docs={'before':before,'after':after};history=[('original',{'manifest':{'dataset_id':'test'},'source_draft_sha256':'before'}),('adopted',{'manifest':{'dataset_id':'test'},'source_draft_sha256':'after'})]
        current=after
        for i,change in enumerate(changes):
            current=deepcopy(current);change(current);key=str(i);docs[key]=current
            history.append((key,{'manifest':{'dataset_id':'test'},'source_draft_sha256':key}))
        doc=dict(before_draft_sha256='before',after_draft_sha256='after',after_registration_sha256='adopted',changed_layer_ids=['head'])
        with patch('autospine_workbench.automation.binding_undo.read_report',side_effect=lambda root,dataset,kind,key:deepcopy(docs[key])):
            return plan_undo(SimpleNamespace(state_root=None),doc,history),current

    def test_other_batch_and_human_notes_are_preserved(self):
        def later(d):
            d['records'][1].update(action='bind',option_id='rigid:foot_l')
            d['records'][2]['notes']='independent human review'
        plan,current=self.fixture([later])
        self.assertTrue(plan['can_undo'])
        self.assertEqual(plan['records'][0]['action'],'pending')
        self.assertEqual(plan['records'][1:],current['records'][1:])

    def test_edited_then_restored_is_not_old_automatic_authority(self):
        plan,_=self.fixture([lambda d:d['records'][0].update(notes='human edit'),lambda d:d['records'][0].update(notes='')])
        self.assertFalse(plan['can_undo'])
        self.assertEqual(plan['reason_code'],'binding_batch_edited_after_adoption')

    def test_source_change_and_already_undone_rejected(self):
        for change in [lambda d:d.update(source_bindings_sha256='different'),lambda d:d['records'][0].update(action='pending',option_id=None)]:
            self.assertFalse(self.fixture([change])[0]['can_undo'])
