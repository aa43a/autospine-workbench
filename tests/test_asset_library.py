"""Catalog lifecycle must not mutate existing project evidence."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.asset_library import AssetLibrary
from autospine_workbench.automation.pipeline_run import PipelineRunError


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = {'id': 'test', 'name': 'Original', 'revision': 7}
        self.store = SimpleNamespace(state_root=Path(self.temp.name),
            list_projects=lambda: [dict(self.source)], get_project=self.get_project)
        self.library = AssetLibrary(self.store)

    def get_project(self, project):
        if project != 'test':
            raise ValueError('not found')
        return dict(self.source)

    def change(self, action, revision, **extra):
        return self.library.change('test', dict(action=action, expected_revision=revision, **extra))

    def test_archive_trash_restore_retains_previous_lifecycle_after_restart(self):
        self.change('archive', 0)
        self.change('trash', 1)
        self.library = AssetLibrary(self.store)
        self.assertEqual(self.library.list()[0]['lifecycle'], 'trashed')
        self.assertEqual(self.change('restore', 2)['lifecycle'], 'archived')
        self.assertEqual(self.change('restore', 3)['lifecycle'], 'active')
        self.assertEqual(self.source, {'id': 'test', 'name': 'Original', 'revision': 7})
        self.assertEqual(len(list((self.library.root / 'test').glob('revision-*.json'))), 4)

    def test_rename_is_display_only_and_conflict_does_not_overwrite(self):
        self.change('rename', 0, name=' 新角色 ')
        row = self.library.list()[0]
        self.assertEqual(row['name'], '新角色')
        self.assertEqual(row['project_revision'], 7)
        with self.assertRaises(PipelineRunError):
            self.change('archive', 0)
        self.assertEqual(self.library.list()[0]['lifecycle'], 'active')

    def test_invalid_mutations_and_traversal_are_rejected(self):
        for body in [dict(action='erase', expected_revision=0),
                     dict(action='rename', expected_revision=0, name=''),
                     dict(action='archive', expected_revision=True),
                     dict(action='restore', expected_revision=0)]:
            with self.assertRaises(PipelineRunError):
                self.library.change('test', body)
        with self.assertRaises(ValueError):
            self.library.metadata('../escape')
        self.assertFalse(self.library.root.exists())
