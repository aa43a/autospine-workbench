from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import json
import unittest

from autospine_workbench.automation.character_auto_audit import overview, save
from autospine_workbench.automation.character_audit_continuity import verified_exceptions
from autospine_workbench.automation.storage_io import canonical_bytes


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root=Path(temp.name)
        self.jobs={}
        self.manager=SimpleNamespace(root=self.root,_lock=RLock(),_path=lambda job:self.root/job,
            get=lambda project,job:deepcopy(self.jobs[job]),verified_files=lambda *_:None,review_file=lambda *_:None)
        self.old=self.add('job-old')

    def add(self, name, project='p', decision='b'*64, artifact='a'*64):
        job=dict(project_id=project,job_id=name,artifact_sha256=artifact,status='needs_review',
            layers=[dict(layer_id='eye',name='eye',state='rigid_reviewed',binding_decision=dict(
                decision_source='policy_auto',evidence_current=True,action='bind',decision_sha256=decision,
                option_id='rigid:head',policy_id='test-v1'))])
        self.jobs[name]=job; folder=self.root/name; folder.mkdir()
        (folder/'result.json').write_bytes(canonical_bytes(job)); return job

    def write(self, job, verdict, **extras):
        current=overview(self.manager,job['project_id'],job['job_id'])
        return save(self.manager,job['project_id'],job['job_id'],dict(
            expected_artifact_sha256=job['artifact_sha256'],expected_review_sha256=current['review_sha256'],
            expected_exception_sha256=current['exception_sha256'],reviews={'eye':verdict},**extras))

    def test_multiple_rebuilds_keep_error_without_inventing_audit_or_timing(self):
        first=self.write(self.old,'incorrect')
        original=(self.root/'job-old/auto-binding-audit/000000.json').read_bytes()
        for name, artifact in [('job-new','a'*64),('job-next','c'*64)]:
            new=self.add(name,artifact=artifact)
            value=overview(self.manager,'p',name)
            self.assertEqual(value['metrics']['carried_exception_layers'],1)
            self.assertEqual(value['metrics']['assessed_bindings'],0)
            self.assertEqual(value['metrics']['default_unreviewed_bindings'],0)
            self.assertIsNone(value['metrics']['audit_session_minutes'])
            self.assertEqual(verified_exceptions(new,value)[0]['source_review_sha256'],first['review_sha256'])
        self.assertEqual((self.root/'job-old/auto-binding-audit/000000.json').read_bytes(),original)

    def test_carried_exception_blocks_acceptance_without_counting_new_audit(self):
        self.write(self.old,'incorrect');new=self.add('job-new')
        new.update(animations=[],runtime={'geometry_status':'passed'})
        audit=overview(self.manager,'p','job-new')
        from autospine_workbench.automation.character_acceptance import assess_character
        from autospine_workbench.automation.character_auto_audit_metrics import summarize
        observation=dict(job=new,auto_binding_audit=audit,verified_runtime={'passed':True},
            visual_review={'aspects':{k:'acceptable' for k in ('setup','draw_order','connections','motion')}})
        result=assess_character(dict(project_id='p',name='test'),observation,[])
        self.assertFalse(result['completed']);self.assertEqual(result['unresolved_layers'],['eye'])
        self.assertEqual(summarize({'p':observation})['assessed_bindings'],0)
        self.assertEqual(summarize({'p':observation})['carried_exception_layers'],1)

    def test_actual_changed_binding_foreign_project_and_stale_evidence_do_not_inherit(self):
        self.write(self.old,'incorrect')
        for name, opts in [('job-changed',{'decision':'d'*64}),('job-other',{'project':'other'})]:
            new=self.add(name,**opts)
            self.assertFalse(verified_exceptions(new,overview(self.manager,new['project_id'],name)))
        new=self.add('job-stale');new['layers'][0]['binding_decision']['evidence_current']=False
        self.assertFalse(verified_exceptions(new,overview(self.manager,'p','job-stale')))

    def test_unrelated_layer_edit_keeps_exception_and_changed_target_does_not(self):
        self.write(self.old,'incorrect');new=self.add('job-new',artifact='c'*64)
        new['layers'].append(dict(layer_id='shirt',name='shirt',state='rigid_reviewed',
            binding_decision=dict(action='bind',option_id='rigid:chest',decision_source='explicit_selection')))
        self.assertEqual(overview(self.manager,'p','job-new')['metrics']['carried_exception_layers'],1)
        new['layers'][0]['binding_decision']['option_id']='rigid:chest'
        self.assertEqual(overview(self.manager,'p','job-new')['metrics']['carried_exception_layers'],0)

    def test_explicit_resolution_survives_next_rebuild_without_rewriting_origin(self):
        old=self.write(self.old,'incorrect');new=self.add('job-new')
        resolved=self.write(new,'correct')
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).parents[1]/'schemas/character-auto-binding-audit-v2.schema.json').read_bytes())
        Draft202012Validator(schema).validate(resolved['review'])
        self.assertFalse(verified_exceptions(new,resolved))
        next_job=self.add('job-next')
        self.assertFalse(verified_exceptions(next_job,overview(self.manager,'p','job-next')))
        self.assertEqual(overview(self.manager,'p','job-old')['review_sha256'],old['review_sha256'])
        # A new explicit error is not erased by the earlier resolution.
        self.write(new,'incorrect')
        self.assertEqual(len(verified_exceptions(next_job,overview(self.manager,'p','job-next'))),1)

    def test_time_only_save_does_not_resolve_or_copy_old_verdict(self):
        self.write(self.old,'incorrect');new=self.add('job-new');current=overview(self.manager,'p','job-new')
        value=save(self.manager,'p','job-new',dict(expected_artifact_sha256=new['artifact_sha256'],
            expected_review_sha256=None,expected_exception_sha256=current['exception_sha256'],reviews={},
            timing=dict(method='operator_stopwatch_v1',scope='automatic_binding_audit_session',seconds=60)))
        self.assertEqual(value['review']['reviews'],{})
        self.assertEqual(value['metrics']['carried_exception_layers'],1)
        self.assertEqual(value['metrics']['assessed_bindings'],0)
        self.assertEqual(value['metrics']['audit_session_minutes'],1)

    def test_unobservable_keeps_exception_default_reset_explicitly_resolves(self):
        self.write(self.old,'incorrect');new=self.add('job-new')
        self.assertEqual(self.write(new,'unobservable')['metrics']['carried_exception_layers'],1)
        self.assertEqual(self.write(new,'not_reviewed')['metrics']['carried_exception_layers'],0)

    def test_scope_and_history_tampering_and_conflicting_write(self):
        self.write(self.old,'incorrect');new=self.add('job-new');value=overview(self.manager,'p','job-new')
        forged=deepcopy(value);forged['exception_continuity']['exceptions'][0]['layer_id']='other'
        self.assertFalse(verified_exceptions(new,forged))
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            save(self.manager,'p','job-new',dict(expected_artifact_sha256='a'*64,expected_review_sha256=None,reviews={'eye':'correct'}))
        path=self.root/'job-old/auto-binding-audit/000000.json'
        doc=json.loads(path.read_bytes());doc['inventory_sha256']='f'*64;path.write_bytes(canonical_bytes(doc))
        with self.assertRaisesRegex(RuntimeError,'history_invalid'):overview(self.manager,'p','job-new')
