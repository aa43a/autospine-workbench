from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from m6_validation_freeze import code_files, digest, verify


class FreezeTests(TestCase):
    def test_effective_code_input_and_file_inventory_drift_are_detected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'src').mkdir()
            code = root/'src/policy.py'; code.write_text('policy=1')
            source = root/'sample.psd'; source.write_bytes(b'original')
            manifest = dict(code=code_files(root), inputs=[dict(path=str(source), sha256=digest(source))])
            self.assertTrue(verify(manifest, root)['passed'])
            code.write_text('policy=2')
            self.assertEqual(verify(manifest, root)['changed_code'], ['src/policy.py'])
            code.write_text('policy=1')
            (root/'src/new.py').write_text('new=1')
            self.assertEqual(verify(manifest, root)['changed_code'], ['src/new.py'])
            (root/'src/new.py').unlink()
            source.write_bytes(b'changed')
            self.assertEqual(verify(manifest, root)['changed_inputs'], [str(source)])
