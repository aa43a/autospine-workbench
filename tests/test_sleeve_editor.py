"""Editor copies preserve candidate identity and reject altered source assets."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from autospine_workbench.resolved_project import canonical_sha256

SPEC = importlib.util.spec_from_file_location(
    'prepare_sleeve_editor', Path(__file__).resolve().parents[1] / 'tools/prepare-sleeve-editor.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SleeveEditorTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'
        bundle = source / 'test' / 'layer-001-component-0000'
        image = 'images/layer-001-component-0000.png'
        assets = {'skeleton.json': json.dumps({'skeleton': {'images': './images/'},
                                             'bones': [{'name': 'root'}]}).encode(),
                  'skeleton.atlas': b'atlas', image: b'fixture texture'}
        for name, raw in assets.items():
            path = bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        report = dict(schema='autospine.sleeve-export-report/v1', project_id='test',
                      authority='none', production_authorized=False, records=[dict(
                          layer_id='layer-001', component_id='component-0000',
                          status='candidate_exported', files={
                              name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()})])
        (source / 'test' / (canonical_sha256(report) + '.json')).write_text(json.dumps(report))
        return source, bundle, assets

    def test_copy_changes_only_images_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, bundle, assets = self.fixture(root)
            result = MODULE.prepare(source, root / 'output', 'test')
            self.assertEqual(result, MODULE.prepare(source, root / 'output', 'test'))
            editor = json.loads(Path(result[0]).read_bytes())
            original = json.loads(assets['skeleton.json'])
            self.assertEqual(editor['skeleton'].pop('images'),
                             (Path(result[0]).parent / 'images').as_posix() + '/')
            original['skeleton'].pop('images')
            self.assertEqual(editor, original)
            for name, raw in assets.items():
                self.assertEqual((bundle / name).read_bytes(), raw)

    def test_changed_asset_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, bundle, _ = self.fixture(root)
            (bundle / 'skeleton.atlas').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'editor_asset_changed'):
                MODULE.prepare(source, root / 'output', 'test')
            self.assertFalse((root / 'output').exists())

    def test_source_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _, _ = self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, 'editor_output_overlaps_source'):
                MODULE.prepare(source, source, 'test')
