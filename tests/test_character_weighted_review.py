from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from autospine_workbench.automation.character_weighted_review import overview, save, confirmed_layers


class WeightedReviewTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        self.layer=dict(layer_id='arm',name='arm',state='weighted_candidate',missing_region_ids=[],
                        regions=[dict(region_id='arm-left',state='weighted_candidate')],
                        binding_decision=dict(decision_source='pending',action='pending'))
        self.result=dict(project_id='p',job_id='j',status='needs_review',artifact_sha256='a'*64,
                         runtime=dict(geometry_status='passed',files={'report.json':'b'*64}),layers=[self.layer])
        self.runtime=dict(bundle_sha256='a'*64,passed=True)
        self.manager=SimpleNamespace(_lock=RLock(),_path=lambda _:root,get=Mock(side_effect=lambda *_:deepcopy(self.result)),
            verified_files=Mock(),review_file=Mock(side_effect=lambda *_:(json.dumps(self.runtime).encode(),'application/json')),
            application=SimpleNamespace(store=SimpleNamespace(read=lambda _:{'character-manifest.json':json.dumps({'layers':self.result['layers']}).encode()})))
        self.body=dict(expected_artifact_sha256='a'*64,expected_review_sha256=None,layer_id='arm',action='confirm')

    def test_confirm_revoke_and_source_are_exact(self):
        before=deepcopy(self.result)
        first=save(self.manager,'p','j',self.body)
        self.assertEqual(confirmed_layers(self.result,first),{'arm'})
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/character-weighted-review-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(first['review'])
        self.assertEqual(self.result,before)
        with self.assertRaisesRegex(RuntimeError,'conflict'):save(self.manager,'p','j',self.body)
        self.body.update(expected_review_sha256=first['review_sha256'],action='revoke')
        second=save(self.manager,'p','j',self.body)
        self.assertEqual(confirmed_layers(self.result,second),set())
        self.assertEqual(second['review']['revision'],1)
        stale=deepcopy(self.result);stale['artifact_sha256']='c'*64
        self.assertEqual(confirmed_layers(stale,first),set())
        self.assertEqual(confirmed_layers(self.result,dict(first,can_review=False)),set())
        self.assertEqual(confirmed_layers(self.result,dict(first,review_sha256='bad')),set())

    def test_partial_missing_and_static_cannot_be_confirmed(self):
        for change in [dict(state='partial'),dict(missing_region_ids=['missing']),
                       dict(regions=[dict(region_id='residual',state='static_reference')]),dict(regions=[])]:
            with self.subTest(change=change):
                old=deepcopy(self.layer);self.layer.update(change)
                with self.assertRaisesRegex(RuntimeError,'scope_invalid'):save(self.manager,'p','j',self.body)
                self.layer.clear();self.layer.update(old)

    def test_failed_runtime_or_geometry_and_changed_layer_evidence_block(self):
        self.runtime['passed']=False
        with self.assertRaisesRegex(RuntimeError,'scope_invalid'):save(self.manager,'p','j',self.body)
        self.runtime['passed']=True;self.result['runtime']['geometry_status']='needs_changes'
        with self.assertRaisesRegex(RuntimeError,'scope_invalid'):save(self.manager,'p','j',self.body)
        self.result['runtime']['geometry_status']='passed'
        first=save(self.manager,'p','j',self.body)
        self.layer['regions'][0]['region_id']='different'
        self.assertEqual(confirmed_layers(self.result,first),set())
        with self.assertRaisesRegex(RuntimeError,'source_mismatch'):overview(self.manager,'p','j')

    def test_unknown_scope_and_unexpected_request_fail(self):
        for body in [dict(self.body,layer_id='other'),dict(self.body,approve=True)]:
            with self.assertRaises(RuntimeError):save(self.manager,'p','j',body)
        self.manager.application.store.read=lambda _:{'character-manifest.json':b'{"layers":[]}'}
        with self.assertRaisesRegex(RuntimeError,'source_mismatch'):overview(self.manager,'p','j')

    def test_cohort_counts_exact_region_review_but_still_requires_visual(self):
        from tests.test_character_cohort import CohortTests
        from autospine_workbench.automation.character_cohort import summarize
        cohort, observations = CohortTests().fixture()
        self.result.update(project_id='a', animations=['idle','wave-left','walk'])
        value=save(self.manager,'a','j',self.body)
        observations['a']=dict(job=self.result,verified_runtime={'passed':True},weighted_review=value)
        row=summarize(cohort,observations)['characters'][0]
        self.assertEqual(row['unresolved_layers'],[])
        self.assertFalse(row['completed'])
        self.assertIn('whole_character_visual_review_required',row['reason_codes'])
        observations['a']['weighted_review']=None
        self.assertEqual(summarize(cohort,observations)['characters'][0]['unresolved_layers'],['arm'])

    def test_pending_with_notes_lineage_can_be_reviewed_only_explicitly(self):
        self.layer['binding_decision']['decision_source']='explicit_selection'
        current=overview(self.manager,'p','j')
        self.assertEqual(current['eligible_layer_ids'],['arm'])
        self.assertEqual(confirmed_layers(self.result,current),set())
        saved=save(self.manager,'p','j',self.body)
        self.assertEqual(confirmed_layers(self.result,saved),{'arm'})
        self.assertEqual(self.layer['binding_decision']['action'],'pending')
