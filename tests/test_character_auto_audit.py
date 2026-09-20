from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest

from autospine_workbench.automation.character_auto_audit import overview, save, summary, verified_reviews
from autospine_workbench.automation.character_auto_audit_metrics import summarize


class AutoAuditTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        layers=[dict(layer_id=key,name=key,binding_decision=dict(decision_source='policy_auto',
            evidence_current=True,action='bind',decision_sha256='b'*64,option_id='rigid:head',policy_id='test-v1'))
            for key in ('eye','brow')]
        self.job=dict(project_id='p',job_id='j',artifact_sha256='a'*64,status='needs_review',layers=layers)
        self.manager=SimpleNamespace(_lock=RLock(),_path=lambda _:root,get=lambda *_:deepcopy(self.job),
                                     verified_files=lambda *_:None,review_file=lambda *_:None)
        self.body=dict(expected_artifact_sha256='a'*64,expected_review_sha256=None,
                       reviews={'eye':'correct','brow':'incorrect'})

    def test_only_explicit_judgments_count_and_do_not_change_bindings(self):
        before=deepcopy(self.job);empty=overview(self.manager,'p','j')
        self.assertIsNone(empty['metrics']['sampled_error_rate'])
        self.assertEqual(empty['metrics']['not_reviewed'],2)
        result=save(self.manager,'p','j',self.body)
        self.assertEqual(result['metrics']['sampled_error_rate'],.5)
        self.assertEqual(result['metrics']['assessed_bindings'],2)
        import json
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/character-auto-binding-audit-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(result['review'])
        self.assertEqual(self.job,before)
        again=save(self.manager,'p','j',dict(self.body,expected_review_sha256=result['review_sha256'],reviews={'brow':'unobservable'}))
        self.assertEqual(again['metrics']['assessed_bindings'],1)
        self.assertEqual(again['metrics']['unobservable'],1)
        self.assertEqual(again['review']['revision'],1)

    def test_atomic_scope_conflict_and_clear(self):
        with self.assertRaisesRegex(RuntimeError,'scope_invalid'):
            save(self.manager,'p','j',dict(self.body,reviews={'eye':'correct','human-layer':'correct'}))
        self.assertIsNone(overview(self.manager,'p','j')['review'])
        result=save(self.manager,'p','j',self.body)
        with self.assertRaisesRegex(RuntimeError,'conflict'):save(self.manager,'p','j',self.body)
        reset=save(self.manager,'p','j',dict(self.body,expected_review_sha256=result['review_sha256'],reviews={'brow':'not_reviewed','eye':'not_reviewed'}))
        self.assertIsNone(reset['metrics']['sampled_error_rate'])

    def test_stale_or_tampered_labels_never_count(self):
        result=save(self.manager,'p','j',self.body)
        stale=dict(self.job,artifact_sha256='c'*64)
        self.assertEqual(verified_reviews(stale,result),{})
        forged=deepcopy(result);forged['review']['reviews']['eye']='incorrect'
        self.assertEqual(verified_reviews(self.job,forged),{})
        self.job['layers'][0]['binding_decision']['option_id']='rigid:chest'
        self.assertEqual(verified_reviews(self.job,result),{})
        with self.assertRaisesRegex(RuntimeError,'history_invalid'):overview(self.manager,'p','j')

    def test_counts_are_per_binding_and_failed_audit_blocks_acceptance(self):
        for layer in self.job['layers']: layer['state']='rigid_reviewed'
        self.job['runtime']={'geometry_status':'passed'}
        self.job['animations']=[]
        from autospine_workbench.automation.character_acceptance import assess_character
        observed=dict(job=self.job,verified_runtime={'passed':True},
            visual_review={'aspects':{k:'acceptable' for k in ('setup','draw_order','connections','motion')}})
        self.assertTrue(assess_character(dict(project_id='p',name='p'),observed,[])['completed'])
        result=save(self.manager,'p','j',self.body)
        metrics=summarize({'p':dict(job=self.job,auto_binding_audit=result)})
        self.assertEqual(metrics['eligible_bindings'],2)
        self.assertEqual(metrics['incorrect'],1)
        report=assess_character(dict(project_id='p',name='p'),dict(observed,auto_binding_audit=result),[])
        self.assertFalse(report['completed'])
        self.assertIn('automatic_binding_audit_needs_changes',report['reason_codes'])
        self.assertIn('brow',report['unresolved_layers'])

    def test_stale_automatic_evidence_is_not_auditable(self):
        self.job['layers'][0]['binding_decision']['evidence_current']=False
        result=overview(self.manager,'p','j')
        self.assertEqual(result['metrics']['eligible_bindings'],1)
        with self.assertRaisesRegex(RuntimeError,'scope_invalid'):save(self.manager,'p','j',self.body)

    def test_measured_audit_time_is_cumulative_preserved_and_source_bound(self):
        timing=dict(method='operator_stopwatch_v1',scope='automatic_binding_audit_session',seconds=90)
        first=save(self.manager,'p','j',dict(self.body,timing=timing))
        import json
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/character-auto-binding-audit-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(first['review'])
        self.assertEqual(first['metrics']['audit_session_minutes'],1.5)
        body=dict(self.body,expected_review_sha256=first['review_sha256'])
        self.assertEqual(save(self.manager,'p','j',body)['review_sha256'],first['review_sha256'])
        with self.assertRaisesRegex(RuntimeError,'timing_regression'):
            save(self.manager,'p','j',dict(body,timing=dict(timing,seconds=89)))
        second=save(self.manager,'p','j',dict(body,timing=dict(timing,seconds=120)))
        metrics=summarize({'p':dict(job=self.job,auto_binding_audit=second)})
        self.assertEqual(metrics['audit_timing']['measured_minutes'],2)
        stale=dict(self.job,artifact_sha256='c'*64)
        self.assertIsNone(summary(stale,second)['audit_session_minutes'])

    def test_invalid_timing_never_creates_history(self):
        for seconds in [True,-1,float('nan'),float('inf'),86401]:
            with self.assertRaisesRegex(RuntimeError,'audit_invalid'):
                save(self.manager,'p','j',dict(self.body,timing=dict(method='operator_stopwatch_v1',scope='automatic_binding_audit_session',seconds=seconds)))
        self.assertIsNone(overview(self.manager,'p','j')['review'])
