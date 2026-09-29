import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from autospine_workbench.automation import runtime_reference_transfer as transfer
from autospine_workbench.automation.storage_io import canonical_bytes


class RuntimeReferenceTransferTests(unittest.TestCase):
    def test_small_and_compressed_transport_preserve_exact_canonical_content(self):
        reference = dict(animations={'motion': [dict(time=0, vertices=[[1.25, 2.75]])]})
        raw = canonical_bytes(reference)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            plain = transfer.write(root, reference)
            self.assertEqual(plain.name, 'runtime-storage-reference.json')
            self.assertEqual(plain.read_bytes(), raw)
            with (patch.object(transfer, 'COMPRESS_AFTER_BYTES', 1),
                  patch.object(transfer.gzip, 'compress', wraps=gzip.compress) as compress):
                packed = transfer.write(root, reference)
                compress.assert_called_once_with(raw, compresslevel=1, mtime=0)
            self.assertEqual(packed.name, 'runtime-storage-reference.json.gz')
            self.assertEqual(gzip.decompress(packed.read_bytes()), raw)

    def test_decoded_limit_rejects_before_compressing_or_writing(self):
        self.assertEqual(transfer.MAX_DECODED_BYTES, 256 * 1024 * 1024)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with (patch.object(transfer, 'MAX_DECODED_BYTES', 4),
                  patch.object(transfer, 'COMPRESS_AFTER_BYTES', 1),
                  patch.object(transfer.gzip, 'compress') as compress):
                with self.assertRaisesRegex(ValueError, 'runtime_storage_reference_limit'):
                    transfer.write(root, dict(exceeds='limit'))
            compress.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__': unittest.main()
