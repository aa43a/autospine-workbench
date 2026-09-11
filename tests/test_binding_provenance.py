"""Automatic lineage survives unrelated edits, but never masks a later selection."""
from copy import deepcopy
import json
from unittest.mock import patch
import unittest
from tests import test_animated_binding_completion as fixtures
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.automation.animated_inputs import save_binding_review
from autospine_workbench.automation.simple_binding_adoption import apply
from autospine_workbench.automation.binding_provenance import read_provenance,attach_provenance


class ProvenanceTests(unittest.TestCase):
    setUp=fixtures.AnimatedCompletionTests.setUp

    def info(self):return inspect_registration(self.store,'fixture')

    def save(self,records):
        save_binding_review(self.store,'fixture',self.info()['source_addresses']['input_identity_sha256'],records)

    def test_lineage_and_later_manual_edits(self):
        records=deepcopy(self.info()['draft']['records']);records[0].update(action='pending',option_id=None);self.save(records)
        def proposal(source):
            rows=[dict(layer_id=r['layer_id'],status='eligible' if i==0 else 'preserved',option_id=source.bindings['bindings'][i]['options'][0]['id'] if i==0 else None)
                  for i,r in enumerate(source.draft['records'])]
            return dict(rows=rows,policy_id='test-transaction',source_addresses=source.source_addresses)
        with patch('autospine_workbench.automation.simple_binding_adoption.propose',proposal):
            decision=apply(self.store,'fixture',self.info()['source_addresses']['input_identity_sha256'])
        original=self.info()['source_addresses']
        report=read_provenance(self.store,'fixture',original)
        self.assertEqual(report['rows'][0]['decision_source'],'policy_auto')
        self.assertEqual(report['rows'][0]['decision_sha256'],decision['decision_sha256'])
        records=deepcopy(self.info()['draft']['records']);records[-1]['notes']='unrelated review';self.save(records)
        current=self.info()['source_addresses'];report=read_provenance(self.store,'fixture',current)
        self.assertEqual(report['rows'][0]['decision_source'],'policy_auto')
        self.assertTrue(report['rows'][0]['evidence_current'])
        with self.assertRaisesRegex(ValueError,'source_changed'):read_provenance(self.store,'fixture',original)
        manifest={'layers':[{'layer_id':r['layer_id']} for r in records],'files':{}}
        files={'character-manifest.json':json.dumps(manifest).encode(),'skeleton.json':b'unchanged'}
        output=attach_provenance(files,self.store,'fixture',current)
        self.assertEqual(output['skeleton.json'],b'unchanged');self.assertNotIn('binding-provenance.json',files)
        self.assertEqual(json.loads(output['character-manifest.json'])['layers'][0]['binding_decision']['decision_source'],'policy_auto')
        records[0]['notes']='explicitly reviewed afterward';self.save(records)
        report=read_provenance(self.store,'fixture',self.info()['source_addresses'])
        self.assertEqual(report['rows'][0]['decision_source'],'explicit_selection')
        self.assertIsNone(report['rows'][0]['decision_sha256'])
