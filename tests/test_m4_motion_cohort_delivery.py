import json
from pathlib import Path
import tempfile
import unittest
from m4_motion_cohort import digest
from m4_motion_cohort_delivery import collect, inventory


class DeliveryCohortTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(motions=[dict(id='walk')], characters=[dict(id='alice')])
        self.job = 'motion-' + '1'*32
        self.state = dict(plan_sha256=digest(self.plan), cells={'walk/alice': dict(
            status='succeeded', job_id=self.job, result=dict(artifact_sha256='a'*64))})

    def test_receipt_resume_does_not_relabel_old_evidence_as_new(self):
        calls = []
        def deliver(job):
            calls.append(job)
            return dict(job_id=job, artifact_sha256='a'*64, archive_files=2)
        with tempfile.TemporaryDirectory() as directory:
            first = collect(self.plan, self.state, Path(directory), deliver, lambda _: None)
            second = collect(self.plan, self.state, Path(directory), deliver, lambda _: None)
        self.assertEqual(calls, [self.job]); self.assertEqual(first, second)

    def test_changed_candidate_does_not_publish_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'receipt_identity'):
                collect(self.plan, self.state, Path(directory),
                        lambda job: dict(job_id=job, artifact_sha256='b'*64), lambda _: None)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_historical_wrong_plan_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/(self.job+'.json')).write_text(json.dumps(dict(plan_sha256='wrong')))
            with self.assertRaisesRegex(ValueError, 'receipt_identity'):
                collect(self.plan, self.state, Path(directory), lambda _: self.fail(), lambda _: None)

    def test_incomplete_and_wrong_plan_are_not_delivery_success(self):
        self.state['cells']['walk/alice']['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'not_complete'): inventory(self.plan, self.state)
        self.state['plan_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'plan_identity'): inventory(self.plan, self.state)
