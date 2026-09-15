"""Registration history, exact authoring checkpoints and explicit review CAS."""
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.automation import animated_inputs as module
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_layer_binding import fixture


class AnimatedInputTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SimpleNamespace(state_root=Path(temporary.name), workspace_root=Path(temporary.name))
        self.checkpoint = {'resolved_project_sha256': 'a' * 64, 'input_identity_sha256': 'b' * 64}
        self.project = {'overrides': {'revision': 0}}
        self.candidate, self.assisted, self.skeleton = fixture()
        self.bindings = build_layer_bindings(self.candidate, self.assisted, self.skeleton)
        self.manifest = {'dataset_id': 'fixture'}
        self.candidate['benchmark_manifest_sha256'] = canonical_sha256(self.manifest)
        self.bindings['candidate_sha256'] = canonical_sha256(self.candidate)
        self.skeleton['candidate_sha256'] = canonical_sha256(self.candidate)
        self.bindings['source_skeleton_sha256'] = canonical_sha256(self.skeleton)
        self.draft = build_layer_binding_draft(self.bindings)
        self.drafts = {canonical_sha256(self.draft): self.draft}
        from autospine_workbench.benchmark.artifacts import publish_report
        for kind, doc in [('semantic-candidates', self.candidate),
                          ('assisted-skeleton-candidates', self.skeleton),
                          ('layer-binding-candidates-v2', self.bindings),
                          ('layer-binding-drafts-v2', self.draft)]:
            publish_report(self.store.state_root, 'fixture', kind, doc)
        for name, value in (
            ('_checkpoint', lambda *_: (deepcopy(self.project), deepcopy(self.checkpoint))),
            ('validate_benchmark_manifest', lambda value: value),
            ('_match_audit', lambda *_: None),
            ('_replay', self.replay),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def replay(self, store, registration):
        sha = registration['source_draft_sha256']
        if sha not in self.drafts:
            from autospine_workbench.benchmark.artifacts import read_report
            self.drafts[sha] = read_report(store.state_root, 'fixture', 'layer-binding-drafts-v2', sha)
        return (self.candidate, self.assisted, self.skeleton, self.bindings,
                self.drafts[sha], b'png', {})

    def register(self):
        return module.register_inputs(self.store, 'project', self.manifest, canonical_sha256(self.draft))

    def test_registration_is_idempotent_and_grants_no_authority(self):
        sha = self.register()
        self.assertEqual(self.register(), sha)
        with module.load_inputs(self.store, 'project') as source:
            self.assertEqual(source.source_addresses['animated_registration_sha256'], sha)
            self.assertEqual(source.draft, self.draft)
            self.assertTrue(all(row['action'] == 'pending' for row in source.draft['records']))
            source.assert_current()

    def test_missing_and_stale_authoring_fail_closed(self):
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_missing'):
            with module.load_inputs(self.store, 'project'):
                pass
        self.register()
        self.checkpoint['resolved_project_sha256'] = 'c' * 64
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_stale'):
            with module.load_inputs(self.store, 'project'):
                pass

    def test_initial_registration_rejects_existing_authoring_edits(self):
        self.project['overrides']['revision'] = 1
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_rebase_required'):
            self.register()

    def test_review_append_undo_and_stale_compare_and_swap(self):
        self.register()
        with module.load_inputs(self.store, 'project') as source:
            initial = source.source_addresses['input_identity_sha256']
        records = deepcopy(self.draft['records'])
        records[0].update(action='semantic_review', option_id=None, notes='Inspect this layer')
        changed = module.save_binding_review(self.store, 'project', initial, records)
        self.assertNotEqual(initial, changed)
        with module.load_inputs(self.store, 'project') as source:
            self.assertEqual(source.draft['records'], records)
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_review_conflict'):
            module.save_binding_review(self.store, 'project', initial, self.draft['records'])
        restored = module.save_binding_review(self.store, 'project', changed, self.draft['records'])
        with module.load_inputs(self.store, 'project') as source:
            self.assertEqual(source.draft, self.draft)
            self.assertEqual(source.source_addresses['input_identity_sha256'], restored)

    def test_registration_tamper_and_history_holes_are_rejected(self):
        self.register()
        root = self.store.state_root / 'animation-inputs' / 'project'
        (root / '000000.json').rename(root / '000001.json')
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_invalid'):
            with module.load_inputs(self.store, 'project'):
                pass

    def test_source_change_during_context_is_detected(self):
        self.register()
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_stale'):
            with module.load_inputs(self.store, 'project'):
                self.checkpoint['input_identity_sha256'] = 'c' * 64

    def test_fast_index_never_replays_and_invalidates_cached_addresses(self):
        from autospine_workbench.automation import animated_input_index as index
        self.register()
        with module.load_inputs(self.store, 'project') as source:
            expected = source.source_addresses
        with patch.object(module, '_replay', side_effect=AssertionError('No full replay')):
            found = index.inspect_registration(self.store, 'project')
            self.assertEqual(found['source_addresses'], expected)
            self.assertEqual(found['verification'], 'registration_only')
            self.assertFalse(found['production_authorized'])
            index.assert_registered_current(self.store, 'project', expected)
            self.checkpoint['input_identity_sha256'] = 'c' * 64
            with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_stale'):
                index.assert_registered_current(self.store, 'project', expected)

    def test_cached_addresses_rejected_after_binding_review(self):
        from autospine_workbench.automation import animated_input_index as index
        self.register()
        with module.load_inputs(self.store, 'project') as source:
            addresses = source.source_addresses
        records = deepcopy(self.draft['records'])
        records[0].update(action='semantic_review', option_id=None, notes='Reconsider')
        module.save_binding_review(self.store, 'project', addresses['input_identity_sha256'], records)
        with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_stale'):
            index.assert_registered_current(self.store, 'project', addresses)

    def test_simultaneous_review_saves_have_one_winner_without_analysis_replay(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from autospine_workbench.automation.animated_input_index import inspect_registration
        self.register()
        initial = inspect_registration(self.store, 'project')['source_addresses']['input_identity_sha256']
        ready = Barrier(2)

        def save(note):
            records = deepcopy(self.draft['records'])
            records[0].update(action='semantic_review', option_id=None, notes=note)
            ready.wait(timeout=10)
            try:
                return module.save_binding_review(self.store, 'project', initial, records)
            except module.AnimatedSourceError as exc:
                return exc.reason_code

        with patch.object(module, '_replay', side_effect=AssertionError('No full replay')):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(save, ['Reviewer A', 'Reviewer B']))
        self.assertEqual(results.count('animated_review_conflict'), 1)
        self.assertEqual(len(module._registrations(self.store, 'project')), 2)


class AnimatedAuditIdentityTests(unittest.TestCase):
    def test_audit_match_also_checks_actual_project_image_bytes(self):
        with TemporaryDirectory() as temporary:
            image = Path(temporary) / 'layer.png'
            image.write_bytes(b'original image bytes')
            audit = {'layers': [{'name': 'sleeve-l'}]}
            candidate = {'audit_snapshot_sha256': canonical_sha256(audit), 'layers': [
                {'name': 'sleeve-l', 'traversal_index': 3,
                 'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}
            store = SimpleNamespace(
                _record=lambda _: SimpleNamespace(audit=audit),
                get_project=lambda _: {'layers': [{'id': 'layer-000-sleeve-l',
                    'name': 'sleeve-l', 'source_index': 3}]},
                resolve_asset=lambda *_: image)
            module._match_audit(store, 'project', candidate)
            image.write_bytes(b'tampered copied image')
            with self.assertRaisesRegex(module.AnimatedSourceError, 'animated_source_mismatch'):
                module._match_audit(store, 'project', candidate)


if __name__ == '__main__':
    unittest.main()
