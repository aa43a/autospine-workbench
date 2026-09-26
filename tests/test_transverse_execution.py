from hashlib import sha256
import unittest
from unittest.mock import patch

from autospine_workbench.automation import motion_repair_execution as execution
from autospine_workbench.automation import motion_repair_draft as draft
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.limb_transverse_scope import PROFILE
import test_motion_repair_execution as queue_fixture
import test_motion_repair_draft as draft_fixture


class TransverseExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=queue_fixture.SubmissionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.row.update(action='transverse_repair',transverse_repair={'bones':['calf_l']})

    def test_save_scope_is_server_derived_and_forged_client_scope_rejected(self):
        f=draft_fixture.RepairDraftTests();f.setUp();self.addCleanup(f.doCleanups)
        body=f.body();body['action']='transverse_repair'
        with patch('autospine_workbench.automation.motion_transverse_repair.scope',return_value={'bones':['calf_l']}):
            saved=draft.save(f.manager,'job',body)
        self.assertEqual(saved['history'][-1]['transverse_repair'],{'bones':['calf_l']})
        self.assertFalse(saved['repair_executed'])
        with self.assertRaisesRegex(RuntimeError,'request_invalid'):
            draft.save(f.manager,'job',dict(body,transverse_repair={'bones':['guessed']}))

    def test_scope_freeze_change_and_withdraw_race(self):
        f=self.fixture;rows=[f.row]
        def resolve(*_):
            self.assertFalse(f.manager._lock._is_owned());return f.row['transverse_repair']
        with patch('autospine_workbench.automation.motion_transverse_repair.scope',side_effect=resolve):
            result=f.invoke()
        request=read_document(f.manager.folder(result['job_id'])/'request.json')
        self.assertEqual(request['repair_execution']['profile'],PROFILE)
        self.assertEqual(request['repair_execution']['draft'],f.row)
        f.manager._pool.submit.reset_mock()
        with patch('autospine_workbench.automation.motion_transverse_repair.scope',return_value={'bones':['other']}):
            with self.assertRaisesRegex(RuntimeError,'scope_changed'):f.invoke()
        def withdraw(*_):rows.append(dict(f.row,action='withdraw',revision=2));return f.row['transverse_repair']
        with patch('autospine_workbench.automation.motion_transverse_repair.scope',side_effect=withdraw):
            with self.assertRaisesRegex(RuntimeError,'plan_changed'):f.invoke(rows=rows)
        f.manager._pool.submit.assert_not_called()
        with patch.object(execution,'submit',return_value={'job_id':'retry'}) as submit:
            execution.retry(f.manager,request)
        self.assertEqual(submit.call_args.args[2]['draft_sha256'],canonical_sha256(f.row))

    def test_other_slot_chain_freezes_parent_and_rejects_repeated_slots(self):
        from autospine_workbench.automation.motion_repair_lineage import carry
        f=self.fixture; parent_plan=dict(f.row,slot='other-leg')
        parent=dict(profile=PROFILE,draft=parent_plan,draft_sha256=canonical_sha256(parent_plan))
        f.request['repair_execution']=parent
        f.manager.folder('parent').joinpath('request.json').write_bytes(canonical_bytes(f.request))
        raw=canonical_bytes(dict(parent,authority='none',selected=False))
        files={'motion-repair-provenance.json':raw,'motion-repair.json':canonical_bytes(dict(profile=PROFILE))}
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'a'*64},files)), \
             patch('autospine_workbench.automation.motion_transverse_repair.scope',return_value=f.row['transverse_repair']):
            result=f.invoke()
            repair=read_document(f.manager.folder(result['job_id'])/'request.json')['repair_execution']
            self.assertEqual(repair['parent_repair_sha256'],sha256(raw).hexdigest())
            self.assertEqual(len(carry(files,repair)),1)
            previous=dict(parent,draft=f.row,draft_sha256=canonical_sha256(f.row))
            prior_raw=canonical_bytes(previous)
            files.update(carry({'motion-repair-provenance.json':prior_raw,'motion-repair.json':b'{}'},
                dict(parent_job_id='earlier',parent_artifact_sha256='previous',parent_repair_sha256=sha256(prior_raw).hexdigest())))
            with self.assertRaisesRegex(RuntimeError,'already_processed'):f.invoke()
            f.row['slot']='other-leg'
            with self.assertRaisesRegex(RuntimeError,'nested_execution'):f.invoke()
