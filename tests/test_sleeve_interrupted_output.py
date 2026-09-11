from pathlib import Path
import tempfile
import unittest
from autospine_workbench.automation.sleeve_interrupted_output import preserve_partial


class InterruptedOutputTests(unittest.TestCase):
    def test_only_unreceipted_current_stage_is_moved_and_bytes_are_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'ordinary-deform';output.mkdir()
            (output/'partial').write_bytes(b'partial')
            complete=root/'weights';complete.mkdir();(complete/'keep').write_bytes(b'unchanged')
            (root/'receipts').mkdir();(root/'receipts/weights.json').write_bytes(b'receipt')
            moved=preserve_partial(root,'ordinary-deform',output)
            self.assertEqual((moved/'partial').read_bytes(),b'partial');self.assertEqual(list(output.iterdir()),[])
            self.assertEqual((complete/'keep').read_bytes(),b'unchanged')
            with self.assertRaisesRegex(ValueError,'completed'):preserve_partial(root,'weights',complete)
            with self.assertRaisesRegex(ValueError,'outside'):preserve_partial(root,'spine',root)
            with self.assertRaisesRegex(ValueError,'outside'):preserve_partial(root,'spine',root.parent/'spine')
