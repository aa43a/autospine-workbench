"""Body choice is registration-scoped and is frozen across M5 worker execution."""
from copy import deepcopy
from pathlib import Path
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation import motion_joint_source as source
from autospine_workbench.automation import motion_related_candidates as related
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
import test_motion_related_evidence as related_fixtures


class JointBodySourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.job = 'motion-'+'a'*32
        self.folder = self.root/'jobs'/'motion-intake-v1'/self.job
        self.folder.mkdir(parents=True)
        fixture = related_fixtures.RelatedEvidenceTests(); fixture.setUp(); self.f = fixture
        self.f.request.update(kind='adapt', job_id=self.job, project_id='alice',
                              character_job_id='rig', source_job_id='motion-'+'b'*32,
                              source_job_sha256='c'*64, name='walk')
        self.main = AnimatedStore(self.root).publish(self.f.base)
        self.parent = dict(kind='adapt', status='succeeded', project_id='alice',
                           character_job_id='rig', result=dict(artifact_sha256=self.main))
        self.write_request(); self.write_parent()
        self.manager = SimpleNamespace(state_root=self.root, folder=lambda _:self.folder,
            get=lambda _:deepcopy(self.parent), _lock=RLock())
        self.f.receipt['source_request_sha256'] = canonical_sha256(self.f.request)
        self.registration = related.register(self.manager, self.job, self.f.files,
                                             self.f.receipt, self.f.runtime, self.f.visual)
        self.current = patch('autospine_workbench.automation.motion_target_jobs.assert_current')
        self.current_check = self.current.start(); self.addCleanup(self.current.stop)

    def write_request(self):
        (self.folder/'request.json').write_bytes(canonical_bytes(self.f.request))

    def write_parent(self):
        (self.folder/'result.json').write_bytes(canonical_bytes(self.parent))

    def frozen(self, registration=None):
        context = source.source_context(self.manager, self.job, registration)
        request = deepcopy(context['request'])
        request.update(job_id='motion-'+'d'*32, joint_execution=dict(parent_job_id=self.job,
            parent_artifact_sha256=context['artifact_sha256'], source_provenance=context['provenance']))
        return context, request

    def test_main_default_preserves_original_parent_and_request(self):
        context, request = self.frozen()
        self.assertEqual(context['files'], self.f.base)
        self.assertEqual(context['parent'], self.parent)
        self.assertEqual(context['artifact_sha256'], self.main)
        self.assertEqual(context['provenance']['kind'], 'main')
        self.assertIsNone(context['related'])
        self.current_check.assert_called_with(self.manager, self.f.request)
        self.assertEqual(self.current_check.call_count, 2)
        self.assertEqual(source.frozen_context(self.root, request), context)
        source.assert_frozen_unchanged(self.root, request)

    def test_registered_body_is_exact_and_reverified_by_worker(self):
        context, request = self.frozen(self.registration)
        self.assertEqual(context['artifact_sha256'], self.f.receipt['candidate_bundle_sha256'])
        self.assertNotEqual(context['artifact_sha256'], self.main)
        self.assertEqual(context['files'], self.f.files)
        self.assertEqual(context['parent'], self.parent)
        self.assertEqual(context['provenance']['registration_sha256'], self.registration)
        self.assertEqual(context['related']['candidate_sha256'], context['artifact_sha256'])
        self.assertEqual(context['related']['receipt'], self.f.receipt)
        self.assertNotIn('visual', context['provenance'])
        with patch.object(related, 'load', wraps=related.load) as load:
            self.assertEqual(source.frozen_context(self.root, request), context)
        self.assertEqual(load.call_count, 1)
        source.assert_frozen_unchanged(self.root, request)

    def test_arbitrary_artifact_or_path_cannot_bypass_registration(self):
        for value, reason in [(self.f.receipt['candidate_bundle_sha256'], 'unregistered'),
                              ('../escape', 'registration_invalid'), ('', 'registration_invalid')]:
            with self.subTest(value=value), self.assertRaisesRegex((RuntimeError, ValueError), reason):
                source.source_context(self.manager, self.job, value)

    def test_legacy_main_request_remains_recoverable(self):
        context, request = self.frozen()
        request['joint_execution'].pop('source_provenance')
        self.assertEqual(source.frozen_context(self.root, request)['files'], context['files'])
        request['joint_execution']['parent_job_id'] = '../../elsewhere'
        with self.assertRaisesRegex(RuntimeError, 'job_id_invalid'):
            source.frozen_context(self.root, request)

    def test_registration_removed_after_enqueue_blocks_worker_and_publication(self):
        _, request = self.frozen(self.registration)
        (self.folder/'related-candidates'/(self.registration+'.json')).unlink()
        for operation in (source.frozen_context, source.assert_frozen_unchanged):
            with self.assertRaisesRegex(ValueError, 'unregistered'):
                operation(self.root, request)

    def test_changed_parent_or_request_is_detected_before_loading_selected_body(self):
        _, request = self.frozen(self.registration)
        self.parent['result']['artifact_sha256'] = 'e'*64; self.write_parent()
        with self.assertRaisesRegex((RuntimeError, ValueError), 'baseline_changed'):
            source.frozen_context(self.root, request)
        self.parent['result']['artifact_sha256'] = self.main; self.write_parent()
        self.f.request['projection'] = {'yaw_degrees':30}; self.write_request()
        with self.assertRaisesRegex((RuntimeError, ValueError), 'baseline_changed'):
            source.frozen_context(self.root, request)

    def test_tampered_frozen_selector_or_effective_request_is_rejected(self):
        _, request = self.frozen(self.registration)
        changed = deepcopy(request)
        changed['joint_execution']['source_provenance']['related_evidence_sha256'] = '0'*64
        with self.assertRaisesRegex(RuntimeError, 'source_provenance_changed'):
            source.frozen_context(self.root, changed)
        changed = deepcopy(request); changed['projection'] = {'yaw_degrees':90}
        with self.assertRaisesRegex(RuntimeError, 'source_request_changed'):
            source.frozen_context(self.root, changed)
        changed = deepcopy(request); changed['joint_execution']['parent_artifact_sha256'] = self.main
        with self.assertRaisesRegex(RuntimeError, 'parent_changed'):
            source.frozen_context(self.root, changed)

    def test_corrupt_candidate_is_not_trusted_by_frozen_digest(self):
        _, request = self.frozen(self.registration)
        artifact = self.f.receipt['candidate_bundle_sha256']
        (AnimatedStore(self.root).root/artifact/'skeleton.json').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'artifact_invalid'):
            source.frozen_context(self.root, request)

    def test_another_camera_receipt_cannot_silently_reuse_parent_camera(self):
        self.f.receipt['source_request_sha256'] = 'f'*64
        registration = related.register(self.manager, self.job, self.f.files,
                                          self.f.receipt, self.f.runtime, self.f.visual)
        with self.assertRaisesRegex(RuntimeError, 'related_source_request_mismatch'):
            source.source_context(self.manager, self.job, registration)

    def test_parent_race_during_full_related_read_is_rejected(self):
        original = related.load
        def load(*args):
            result = original(*args)
            self.parent['result']['artifact_sha256'] = 'e'*64
            return result
        with patch.object(related, 'load', side_effect=load):
            with self.assertRaisesRegex(RuntimeError, 'parent_changed'):
                source.source_context(self.manager, self.job, self.registration)

    def test_joint_result_cannot_be_reapplied_as_body(self):
        self.f.request['joint_execution'] = {'parent_job_id':'old'}; self.write_request()
        with self.assertRaisesRegex(RuntimeError, 'original_body_required'):
            source.source_context(self.manager, self.job)


if __name__ == '__main__': unittest.main()
