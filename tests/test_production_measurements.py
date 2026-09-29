from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest import TestCase

from autospine_workbench.automation.production_journal import ProductionJournal
from autospine_workbench.automation.production_measurements import overview,save,metrics


class MeasurementTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        journal=ProductionJournal(Path(self.tmp.name)/'production')
        self.manager=SimpleNamespace(journal=journal,_lock=RLock(),get=journal.read)
        row=journal.create(dict(project_id='p'))
        self.run=row['run_id'];row['created_at']='2026-01-01T00:00:00+00:00'
        journal.append(row,'fixture_history')
        now=datetime.now(timezone.utc)
        self.segment=dict(session_id='a'*32,stage='joints',started_at=(now-timedelta(seconds=120)).isoformat(),
            ended_at=(now-timedelta(seconds=60)).isoformat(),seconds=60,method='operator_stopwatch_segment_v1')

    def record(self,payload,action='record',current=None):
        value=current or overview(self.manager,self.run)
        return save(self.manager,self.run,dict(expected_head_sha256=value['head_sha256'],
            expected_source_sha256=value['source_sha256'],action=action,payload=payload))

    def test_unmeasured_is_null_and_revoke_does_not_erase_history(self):
        self.assertIsNone(metrics(self.manager,self.run)['human']['recorded_minutes'])
        value=self.record(self.segment)
        self.assertEqual(value['metrics']['recorded_minutes'],1)
        self.assertIsNone(value['metrics']['total_human_minutes'])
        path=self.manager.journal.folder(self.run)/'measurements/000000.json';old=path.read_bytes()
        self.record('a'*32,'revoke')
        self.assertEqual(path.read_bytes(),old)
        self.assertIsNone(metrics(self.manager,self.run)['human']['recorded_minutes'])

    def test_stale_overlap_duplicate_and_invalid_clock_rejected(self):
        first=overview(self.manager,self.run);self.record(self.segment)
        with self.assertRaisesRegex(RuntimeError,'conflict'):self.record(self.segment,current=first)
        with self.assertRaisesRegex(RuntimeError,'duplicate'):self.record(self.segment)
        with self.assertRaisesRegex(RuntimeError,'overlap'):self.record(dict(self.segment,session_id='b'*32))
        future=datetime.now(timezone.utc)+timedelta(days=1)
        with self.assertRaisesRegex(RuntimeError,'outside_run'):
            self.record(dict(self.segment,session_id='c'*32,started_at=future.isoformat(),ended_at=(future+timedelta(seconds=60)).isoformat()))

    def test_retries_are_separate_intervals_not_fabricated_human_interventions(self):
        row=self.manager.get(self.run)
        row['stages']['body'].update(job_id='old',started_at='2026-01-01T00:00:00+00:00',
            finished_at='2026-01-01T00:01:00+00:00',status='failed')
        row.update(status='blocked',reason_code='failed')
        row=self.manager.journal.append(row,'body_finished')
        row=self.manager.journal.append(row,'observed_again')
        row=self.manager.journal.append(row,'retry_requested')
        row['stages']['body'].update(job_id='new',started_at='2026-01-01T00:02:00+00:00',
            finished_at='2026-01-01T00:03:00+00:00',status='succeeded')
        row['status']='needs_review';self.manager.journal.append(row,'body_finished')
        report=metrics(self.manager,self.run)
        self.assertEqual(len(report['observed_child_intervals']),2)
        self.assertEqual(report['retry_requests'],1);self.assertEqual(report['blocked_observations'],1)
        self.assertIsNone(report['intervention_count']);self.assertIsNone(report['automatic_compute_seconds'])
        self.assertIsNone(report['waiting_seconds'])

    def test_worker_elapsed_is_distinct_from_observed_wall_interval(self):
        job='motion-'+'a'*32
        self.manager.driver=SimpleNamespace(motions=SimpleNamespace(get=lambda *a,**k:dict(
            job_id=job,status='succeeded',elapsed_seconds=12.5)))
        row=self.manager.get(self.run)
        row['stages']['body'].update(job_id=job,started_at='2026-01-01T00:00:00+00:00',
            finished_at='2026-01-01T00:01:00+00:00',status='succeeded')
        self.manager.journal.append(row,'body_finished')
        report=metrics(self.manager,self.run)
        self.assertEqual(report['recorded_execution_seconds'],12.5)
        self.assertEqual(report['execution_measured_attempts'],1)
        self.assertEqual(report['observed_child_intervals'][0]['seconds'],60)
        self.assertIsNone(report['human']['recorded_minutes'])
        self.assertIsNone(report['automatic_compute_seconds'])
