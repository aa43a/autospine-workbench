"""Bounded orchestration only; policy correctness is tested by the policy suites."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import json
from autospine_workbench.automation.binding_auto_run import apply_all
from autospine_workbench.automation.animated_inputs import AnimatedSourceError


class BindingAutoRunTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup);self.store=SimpleNamespace(state_root=Path(tmp.name))
        self.revision=0;self.selected=[];self.fail=False
        @contextmanager
        def source(*_):yield SimpleNamespace(source_addresses={'input_identity_sha256':str(self.revision)})
        def proposal(_):
            eligible=['head','neck'] if self.revision==0 else ['eye'] if self.revision==1 else []
            return {'rows':[dict(layer_id=k,status='eligible') for k in eligible]+[dict(layer_id='sleeve',status='needs_review'),dict(layer_id='manual',status='preserved')]}
        def apply(_,project,expected):
            self.assertEqual(expected,str(self.revision))
            if self.fail and self.revision==1:raise OSError('interrupted')
            changed=['head','neck'] if self.revision==0 else ['eye'];self.selected+=changed;self.revision+=1
            return dict(changed=True,changed_layer_ids=changed,decision_sha256=str(self.revision)*64)
        for name,fn in [('load_inputs',source),('propose',proposal),('apply',apply)]:
            mock=patch('autospine_workbench.automation.binding_auto_run.'+name,side_effect=fn);mock.start();self.addCleanup(mock.stop)

    def test_one_request_handles_dependencies_and_then_becomes_idempotent(self):
        r=apply_all(self.store,'p','0');self.assertEqual(r['rounds'],2)
        self.assertEqual(r['changed_layer_ids'],['eye','head','neck'])
        self.assertEqual(r['status'],'succeeded');self.assertFalse(r['production_authorized'])
        self.assertEqual(len(r['batches']),2)
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).parents[1]/'schemas/binding-auto-run-v1.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(r)
        self.assertFalse(apply_all(self.store,'p','2')['changed'])

    def test_stale_input_cannot_start_and_interruption_keeps_committed_receipts(self):
        with self.assertRaisesRegex(AnimatedSourceError,'conflict'):apply_all(self.store,'p','stale')
        self.assertEqual(self.selected,[])
        self.fail=True;r=apply_all(self.store,'p','0')
        self.assertEqual(r['status'],'stopped');self.assertEqual(r['rounds'],1)
        self.assertEqual(r['changed_layer_ids'],['head','neck'])

    def test_repeated_eligibility_and_round_limit_stop_without_looping(self):
        with patch('autospine_workbench.automation.binding_auto_run.propose',return_value={'rows':[dict(layer_id=k,status='eligible') for k in ['head','neck']]}):
            r=apply_all(self.store,'p','0');self.assertEqual(r['reason_code'],'binding_auto_no_progress')
        self.revision=0
        with patch('autospine_workbench.automation.binding_auto_run.MAX_ROUNDS',1):
            self.assertEqual(apply_all(self.store,'p','0')['reason_code'],'binding_auto_round_limit')
