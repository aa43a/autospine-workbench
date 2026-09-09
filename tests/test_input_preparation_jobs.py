"""Preparation recovery, cancellation and registration are separate states."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import time
import unittest

from autospine_workbench.automation.input_preparation_jobs import InputPreparationJobs, response
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import publish_document


class PreparationDouble:
    def __init__(self):
        self.entered, self.release = Event(), Event()

    def prepare(self, *, project_id, expected_resolved_sha256, cancel_requested, progress):
        self.entered.set()
        progress([{'id': 'run-pose', 'status': 'running'}])
        self.release.wait(4)
        return {'status': 'canceled' if cancel_requested() else 'needs_review',
                'source_registered': not cancel_requested(), 'authority': 'none',
                'input_identity_sha256': 'd' * 64}


class InputPreparationJobTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SimpleNamespace(state_root=Path(temporary.name))
        self.app = PreparationDouble()
        self.manager = InputPreparationJobs(self.store, self.app)
        self.addCleanup(self.manager.close)
        self.addCleanup(self.app.release.set)

    def terminal(self, job):
        for _ in range(100):
            value = self.manager.get('project', job['job_id'])
            if value['status'] not in ('pending', 'running'):
                return value
            time.sleep(.02)
        self.fail('Preparation failed to terminate')

    def test_dedup_cancel_and_project_isolation(self):
        job = self.manager.submit('project', 'a' * 64)
        self.assertTrue(self.app.entered.wait(2))
        self.assertEqual(self.manager.submit('project', 'a' * 64)['job_id'], job['job_id'])
        with self.assertRaisesRegex(PipelineRunError, 'pipeline_job_not_found'):
            self.manager.cancel('other', job['job_id'])
        self.assertTrue(self.manager.cancel('project', job['job_id'])['cancel_requested'])
        self.app.release.set()
        value = self.terminal(job)
        self.assertEqual(value['status'], 'canceled')
        self.assertFalse(value['source_registered'])

    def test_completed_result_survives_manager_restart(self):
        self.app.release.set()
        job = self.manager.submit('project', 'a' * 64)
        value = self.terminal(job)
        self.assertEqual(value['status'], 'needs_review')
        self.assertTrue(value['source_registered'])
        other = InputPreparationJobs(self.store, self.app)
        self.addCleanup(other.close)
        self.assertEqual(other.get('project', job['job_id']), value)

    def test_interrupted_request_and_rebound_receipt(self):
        job_id = 'job-' + 'b' * 32
        folder = self.manager._path(job_id, True)
        request = {'project_id': 'project', 'expected_resolved_sha256': 'a' * 64}
        publish_document(folder / 'request.json', request, staging=folder / 'staging')
        self.assertEqual(self.manager.get('project', job_id)['reason_code'], 'preparation_interrupted')
        value = response(job_id, {**request, 'expected_resolved_sha256': 'c' * 64}, 'needs_review')
        publish_document(folder / 'result.json', value, staging=folder / 'staging')
        with self.assertRaisesRegex(PipelineRunError, 'pipeline_storage_invalid'):
            self.manager.get('project', job_id)

    def test_rejects_nested_registration_and_authority_forgery(self):
        for index, nested in enumerate([
            {'status': 'canceled', 'source_registered': False, 'authority': 'none'},
            {'status': 'needs_review', 'source_registered': True, 'authority': 'approved'},
        ]):
            job_id = 'job-' + str(index) * 32
            folder = self.manager._path(job_id, True)
            request = {'project_id': 'project', 'expected_resolved_sha256': 'a' * 64}
            value = response(job_id, request, 'needs_review')
            value.update(source_registered=True, result=nested)
            publish_document(folder / 'request.json', request, staging=folder / 'staging')
            publish_document(folder / 'result.json', value, staging=folder / 'staging')
            with self.assertRaisesRegex(PipelineRunError, 'pipeline_storage_invalid'):
                self.manager.get('project', job_id)
