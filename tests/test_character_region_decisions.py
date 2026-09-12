from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import json
import unittest
from test_character_region_exclusion import fixture
from autospine_workbench.automation.character_region_decisions import overview, save, apply_saved
from autospine_workbench.automation.storage_io import canonical_bytes
from hashlib import sha256


class RegionDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.files, _ = fixture(); self.packages = {'a'*64: self.files}
        def publish(files):
            digest = sha256(canonical_bytes({n: sha256(raw).hexdigest() for n, raw in files.items()})).hexdigest()
            self.packages[digest] = files; return digest
        self.manager = SimpleNamespace(root=Path(self.temp.name), _lock=RLock(),
            projects=SimpleNamespace(get_project=lambda _: None),
            application=SimpleNamespace(store=SimpleNamespace(read=self.packages.__getitem__, publish=publish)),
            get=lambda *_: dict(status='needs_review', artifact_sha256='a'*64), download=lambda *_: b'checked')
        self.body = dict(action='exclude', expected_head_sha256=None, job_id='job', expected_artifact_sha256='a'*64,
                         layer_id='source', region_id='rest')

    def test_save_rebuild_and_revoke_restore_original_without_erasing_history(self):
        result = dict(artifact_sha256='a'*64, manifest=json.loads(self.files['character-manifest.json']))
        current = save(self.manager, 'project', self.body)
        built = apply_saved(self.manager, 'project', result, current['head_sha256'])
        self.assertNotEqual(built['artifact_sha256'], result['artifact_sha256'])
        self.assertEqual(built['manifest']['layers'][0]['state'], 'weighted_candidate')
        revoked = save(self.manager, 'project', dict(action='revoke', expected_head_sha256=current['head_sha256'],
                                                   decision_sha256=current['active'][0]['decision_sha256']))
        self.assertEqual(revoked['active'], [])
        self.assertEqual(apply_saved(self.manager, 'project', result, revoked['head_sha256']), result)
        self.assertEqual(len(list((self.manager.root/'region-decisions/project').glob('*.json'))), 2)

    def test_stale_writer_and_running_snapshot_rejected(self):
        save(self.manager, 'project', self.body)
        with self.assertRaisesRegex(RuntimeError, 'conflict'):
            save(self.manager, 'project', self.body)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            apply_saved(self.manager, 'project', {}, None)

    def test_changed_source_does_not_silently_reuse_decision(self):
        current = save(self.manager, 'project', self.body)
        changed = dict(self.files); manifest = json.loads(changed['character-manifest.json']); manifest['new_source'] = True
        changed['character-manifest.json'] = canonical_bytes(manifest); self.packages['b'*64] = changed
        with self.assertRaisesRegex(RuntimeError, 'source_changed'):
            apply_saved(self.manager, 'project', dict(artifact_sha256='b'*64), current['head_sha256'])
        self.assertEqual(overview(self.manager, 'project'), current)
