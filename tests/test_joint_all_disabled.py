"""Independent all-off invariant across the two real channel compilers."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43 import joint_face, joint_secondary
from test_joint_secondary import scene


class JointAllDisabledTests(unittest.TestCase):
    def test_all_disabled_preserves_skeleton_and_every_original_asset_byte(self):
        files, document = scene()
        files['skeleton.json'] = canonical_bytes(document)
        # Include atlas and an unrelated user asset so isolation covers file maps.
        files['skeleton.atlas'] = b'original atlas kept byte for byte\r\n'
        files['user-note.txt'] = b'keep\x00\xff'
        before = deepcopy(files)
        face, updates, face_report = joint_face.apply(files, document, 'idle', joint_face.defaults(), [0., 1., 2.])
        combined, secondary_report = joint_secondary.apply(files, face, 'idle', joint_secondary.defaults(), [0., 1., 2.])
        output = {**files, **updates, 'skeleton.json': canonical_bytes(combined)}
        self.assertEqual(output, before)
        self.assertEqual(face_report['status'], 'disabled')
        self.assertEqual(secondary_report['status'], 'disabled')

    def test_all_off_real_character_preserves_exported_binding_document(self):
        root = Path('workspace/builds/animated-preview-v1/6e5c59db4ef072075b798efab12acf8ffdc883368a61a4bf3c1646305ef68b98')
        if not root.is_dir(): self.skipTest('local Alice artifact unavailable')
        files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        raw = files['skeleton.json']; document = json.loads(raw)
        face, updates, _ = joint_face.apply(files, document, 'idle', joint_face.defaults(), [0., 1., 2.])
        output, _ = joint_secondary.apply(files, face, 'idle', joint_secondary.defaults(), [0., 1., 2.])
        self.assertEqual(output, document)
        self.assertEqual(canonical_bytes(output), raw)
        self.assertEqual(updates, {})
        self.assertEqual(files['skeleton.json'], raw)


if __name__ == '__main__':
    unittest.main()
