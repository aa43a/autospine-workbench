"""Offline addon input locks and archive boundaries; no inference claim."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

packaging_root = Path(__file__).resolve().parents[1] / 'packaging'
sys.path.insert(0, str(packaging_root))
try:
    spec = importlib.util.spec_from_file_location('studio_pose_runtime', packaging_root/'prepare_pose_runtime.py')
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)
finally:
    sys.path.remove(str(packaging_root))


class StudioPoseRuntimeTests(unittest.TestCase):
    def test_lock_rejects_changed_artifact_hash_even_with_same_upstream_version(self):
        document = json.loads((packaging_root/'pose-runtime-wheels.lock.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'lock.json'
            file.write_text(json.dumps(document))
            self.assertEqual(len(addon.wheel_lock(file)), 7)
            for field, value in [('sha256', 'f'*64), ('version', '9.0'), ('url', 'https://example.com/tool.whl')]:
                bad = copy.deepcopy(document)
                bad['wheels'][0][field] = value
                file.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    addon.wheel_lock(file)

    def test_lock_rejects_duplicate_packages_and_unknown_fields(self):
        document = json.loads((packaging_root/'pose-runtime-wheels.lock.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'lock.json'
            document['wheels'][-1] = copy.deepcopy(document['wheels'][0])
            file.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                addon.wheel_lock(file)
            document = json.loads((packaging_root/'pose-runtime-wheels.lock.json').read_text())
            document['wheels'][0]['command'] = 'pip install unpinned'
            file.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                addon.wheel_lock(file)

    def test_wheel_extraction_rejects_external_paths_non_fixed_roots_and_executables(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for index, name in enumerate(('../outside.py', 'numpy/../../outside.py', 'foreign/module.py', 'cv2/run.exe')):
                wheel = root/f'{index}.whl'
                with zipfile.ZipFile(wheel, 'x') as zipped:
                    zipped.writestr(name, b'untrusted fixture')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    addon.extract_wheel(wheel, root/f'output-{index}')
            self.assertFalse((root.parent/'outside.py').exists())

    def test_an_existing_destination_is_preserved_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'preserve.txt').write_bytes(b'old software')
            missing = root/'missing'
            with self.assertRaisesRegex(ValueError, 'destination already exists'):
                addon.prepare(missing, missing, missing, missing, missing, missing, root)
            self.assertEqual((root/'preserve.txt').read_bytes(), b'old software')

    def test_archive_detects_changed_inventory_and_preserves_existing_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'source'
            root.mkdir()
            (root/'provenance.json').write_bytes(b'{}')
            (root/addon.MANIFEST).write_text(json.dumps({'files': addon.inventory(root)}))
            output = Path(folder)/'bundle.zip'
            result = addon.archive(root, output)
            self.assertTrue(result['verified'])
            old = output.read_bytes()
            with self.assertRaisesRegex(ValueError, 'archive exists'):
                addon.archive(root, output)
            self.assertEqual(output.read_bytes(), old)
            (root/'provenance.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                addon.archive(root, Path(folder)/'new.zip')


if __name__ == '__main__':
    unittest.main()
