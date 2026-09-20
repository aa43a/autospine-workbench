"""SOMA77 intake preserves bytes, explicit interpretation, labels and rig geometry."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_kimodo_intake import compile_source, options
from autospine_workbench.automation.motion_target_worker import execute
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.kimodo_npz_reader import inspect_kimodo_npz_profile
from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes, build_npy
from test_motion_target_intake import inputs

SETTINGS = dict(profile='kimodo-soma77-v1', fps='30')


class KimodoIntakeTests(unittest.TestCase):
    def test_unsafe_members_and_wrong_skeleton_rejected(self):
        members = motion_member_bytes()
        for change in ({'unexpected.npy': b'ignored'},
                       {'posed_joints.npy': build_npy('|O', (3, 77, 3), b'pickle')},
                       {'posed_joints.npy': build_npy('<f4', (3, 30, 3), bytes(3*30*3*4))}):
            with self.subTest(change=list(change)):
                with self.assertRaises(ValueError):
                    inspect_kimodo_npz_profile(build_npz(dict(members, **change)))

    def test_profile_and_rate_never_inferred_from_npz_shape(self):
        for profile, rate in [(None, '30'), ('smplx', '30'), ('kimodo-soma77-v1', 'nan'),
                              ('kimodo-soma77-v1', '0'), ('kimodo-soma77-v1', '1000001/4000')]:
            with self.assertRaises(PipelineRunError):
                options(profile, rate)
        self.assertEqual(options('kimodo-soma77-v1', '29.97')['fps'], '2997/100')

    def test_real_child_and_retry_preserve_interpretation_and_contact_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            jobs = MotionIntakeJobs(SimpleNamespace(state_root=Path(temporary)))
            self.addCleanup(jobs.close)
            raw = build_npz(motion_member_bytes(contacts=6))
            first = jobs.upload(BytesIO(raw), len(raw), '挥手.npz', 'front', SETTINGS)
            done = self.wait(jobs, first)
            self.assertEqual(done['status'], 'succeeded', done)
            result = done['result']
            self.assertEqual(result['motion_status'], 'compiled', result)
            self.assertEqual(result['contact_status'], 'source_labels_annotation_only')
            self.assertEqual(result['producer_status'], 'unavailable_external_export')
            verified = VerifiedMotionBundleReader(Path(temporary)).load(
                result['motion']['clip_sha256'], result['motion']['bundle_sha256'])
            self.assertEqual(verified.raw_npz, raw)
            self.assertTrue(verified.motion['markers'])
            preview = json.loads(jobs.preview(first['job_id']))
            self.assertEqual(len(preview['names']), 77)
            self.assertAlmostEqual(preview['frames'][-1]['time'], 2/30)
            again = self.wait(jobs, jobs.retry(first['job_id']))
            self.assertEqual(again['status'], 'succeeded', again)
            self.assertNotEqual(again['job_id'], first['job_id'])
            self.assertEqual(again['result']['motion']['bundle_sha256'], result['motion']['bundle_sha256'])
            self.assertEqual(jobs.get(first['job_id']), done)

    def test_matrix_inconsistency_does_not_generate_motion(self):
        raw = build_npz(motion_member_bytes(posed_overrides={(1, 'LeftHand'): (999, 999, 999)}))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'source.npz').write_bytes(raw)
            with self.assertRaises(ValueError):
                compile_source(raw, dict(npz_options=SETTINGS, view='front'), root, root/'state')
            self.assertFalse((root/'state/motions').exists())

    def test_target_uses_npz_without_bvh_and_retains_reviewed_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake, target = root/'intake', root/'target'
            intake.mkdir(); target.mkdir()
            raw = build_npz(motion_member_bytes())
            (intake/'source.npz').write_bytes(raw)
            identity = compile_source(raw, dict(npz_options=SETTINGS, view='front'), intake, root)['motion']
            files = inputs()[0]
            doc = json.loads(files['skeleton.json'])
            for name, parent in [('spine', 'root'), ('chest', 'spine'), ('neck', 'chest'),
                                 ('head', 'neck'), ('clavicle_l', 'chest'), ('clavicle_r', 'chest')]:
                doc['bones'].append(dict(name=name, parent=parent, x=0, y=10, rotation=0))
            files['skeleton.json'] = canonical_bytes(doc)
            store = AnimatedStore(root)
            original = store.publish(files)
            (target/'request.json').write_bytes(canonical_bytes(dict(motion_identity=identity, character_sha256=original)))
            with patch('autospine_workbench.automation.motion_target_worker.capture', return_value=dict(status='unavailable')):
                execute(target, root, root)
            result = read_document(target/'worker-result.json')
            self.assertEqual(store.read(original), files)
            candidate = store.read(result['artifact_sha256'])
            evidence = json.loads(candidate['motion-review.json'])
            self.assertIn('projected_lengths', evidence)
            self.assertEqual(json.loads(candidate['motion-ir.json'])['markers'],
                             VerifiedMotionBundleReader(root).load(identity['clip_sha256'], identity['bundle_sha256']).motion['markers'])

    def wait(self, jobs, job):
        deadline = time.monotonic()+25
        while time.monotonic() < deadline:
            value = jobs.get(job['job_id'])
            if value['status'] not in ('pending', 'running'):
                return value
            time.sleep(.02)
        self.fail('child did not finish')
