"""Audit migration preserves existing bytes and never consumes embedded paths."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from autospine_workbench.automation.animated_cli import import_audit
from autospine_workbench.manifest_artifacts import LayerManifestError


class AnimatedCliTests(unittest.TestCase):
    def test_import_is_idempotent_and_only_copies_local_resources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            audit = b'{"path":"../../outside.png"}'
            (source / 'audit.json').write_bytes(audit)
            (source / 'layer.png').write_bytes(b'exact source bytes')
            (source / 'run.ps1').write_text('not an imported resource')
            store = SimpleNamespace(audit_root=root / 'projects')
            for _ in range(2):
                import_audit(store, 'fixture', source)
            target = store.audit_root / 'fixture'
            self.assertEqual((target / 'audit.json').read_bytes(), audit)
            self.assertEqual((target / 'layer.png').read_bytes(), b'exact source bytes')
            self.assertFalse((target / 'run.ps1').exists())
            self.assertFalse((root / 'outside.png').exists())
            (source / 'layer.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'animated_audit_conflict'):
                import_audit(store, 'fixture', source)
            self.assertEqual((target / 'layer.png').read_bytes(), b'exact source bytes')

    def test_invalid_project_id_cannot_escape_import_root(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = SimpleNamespace(audit_root=root / 'projects')
            with self.assertRaises(LayerManifestError):
                import_audit(store, '../escape', root)
            self.assertFalse((root / 'escape').exists())

    def test_missing_audit_does_not_publish_partial_project(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'layer.png').write_bytes(b'original')
            store = SimpleNamespace(audit_root=root / 'projects')
            with self.assertRaisesRegex(ValueError, 'animated_audit_missing'):
                import_audit(store, 'fixture', source)
            self.assertFalse(store.audit_root.exists())


if __name__ == '__main__':
    unittest.main()
