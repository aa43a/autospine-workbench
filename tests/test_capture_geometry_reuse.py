from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.capture_geometry import prepared, reuse
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes


def fixture():
    files = {'skeleton.json': b'{}', 'numeric-reference.json': b'bounded-reference'}
    geometry = dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), passed=True, records=[])
    files['deformation.json'] = canonical_bytes(geometry)
    return files, geometry


class CaptureGeometryReuseTests(unittest.TestCase):
    def test_reuse_binds_geometry_and_every_reference_file(self):
        files, geometry = fixture()
        proof = prepared(files, geometry)
        self.assertEqual(reuse(proof, files, proof.bundle_sha256), geometry)
        for name in files:
            changed = dict(files, **{name: files[name] + b' '})
            with self.assertRaisesRegex(ValueError, 'source_mismatch'):
                reuse(proof, changed, proof.bundle_sha256)
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            reuse(proof, files, '0' * 64)
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            prepared(files, dict(geometry, passed=False))

    def test_reuse_skips_only_duplicate_geometry_and_count_decode(self):
        files, geometry = fixture()
        proof = prepared(files, geometry)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = Mock(root=root); store.read.return_value = files
            stages = []
            storage = dict(animations={'body': [{'time': 0}, {'time': 1}]})
            def run(command, **kwargs):
                (root/'runtime/report.json').write_bytes(canonical_bytes(dict(
                    bundle_sha256=proof.bundle_sha256, authority='none', production_authorized=False,
                    results=[{}, {}], scope='official_runtime', info=dict(slots=1))))
                return SimpleNamespace(returncode=0)
            with (patch('autospine_workbench.automation.character_capture.discover',
                        return_value=('node', 'deps', None, 'browser')),
                  patch('autospine_workbench.targets.character43.static_region_review.build', return_value=({}, {})),
                  patch('autospine_workbench.targets.character43.deformation_qa.inspect') as inspect,
                  patch('autospine_workbench.targets.character43.numeric_reference.read') as read,
                  patch('autospine_workbench.targets.character43.runtime_storage_reference.build', return_value=storage) as build,
                  patch('autospine_workbench.automation.character_capture.subprocess.run', side_effect=run) as launch):
                result = capture(SimpleNamespace(workspace_root=root), store, proof.bundle_sha256, root,
                    progress=stages.append, cancel_requested=lambda: False, storage_reference=True,
                    geometry_evidence=proof)
            inspect.assert_not_called(); read.assert_not_called()
            build.assert_called_once_with(files)
            self.assertEqual(launch.call_count, 2)
            self.assertEqual(result['frames'], 2)
            self.assertEqual(result['geometry_status'], 'passed')
            self.assertEqual(stages, ['runtime_prepare', 'runtime_geometry', 'runtime_reference', 'runtime', 'runtime_setup'])

    def test_reuse_still_checks_joint_parent_before_launch(self):
        files, geometry = fixture()
        files['joint-animation.json'] = canonical_bytes(dict(
            skeleton_sha256=geometry['skeleton_sha256'], parent_skeleton_sha256='0' * 64))
        files['joint-provenance.json'] = canonical_bytes(dict(parent_artifact_sha256='1' * 64))
        proof = prepared(files, geometry)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = Mock(root=root); store.read.return_value = files
            store.read_file.return_value = b'changed-parent'
            with (patch('autospine_workbench.automation.character_capture.discover',
                        return_value=('node', 'deps', None, 'browser')),
                  patch('autospine_workbench.targets.character43.static_region_review.build', return_value=({}, {})),
                  patch('autospine_workbench.targets.character43.deformation_qa.inspect') as inspect,
                  patch('autospine_workbench.automation.character_capture.subprocess.run') as launch):
                with self.assertRaisesRegex(ValueError, 'capture_parent_mismatch'):
                    capture(SimpleNamespace(workspace_root=root), store, proof.bundle_sha256, root,
                        progress=lambda step: None, cancel_requested=lambda: False, storage_reference=True,
                        geometry_evidence=proof)
            inspect.assert_not_called(); launch.assert_not_called()


if __name__ == '__main__': unittest.main()
