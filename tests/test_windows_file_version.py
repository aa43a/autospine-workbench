from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.windows_file_version as subject
from autospine_workbench.windows_file_version import read_windows_file_version


class WindowsFileVersionTests(unittest.TestCase):
    def test_decodes_fixed_file_version_words(self) -> None:
        self.assertEqual(
            (151, 0, 7922, 174),
            subject._decode_file_version((151 << 16), (7922 << 16) | 174),
        )

    def test_rejects_out_of_buffer_ranges(self) -> None:
        buffer = ctypes.create_string_buffer(16)
        start = ctypes.addressof(buffer)
        subject._require_buffer_range(buffer, 16, start + 4, 8, ctypes)
        invalid = ((start - 1, 1), (start + 12, 8), (start, 0))
        for pointer, length in invalid:
            with self.subTest(pointer=pointer, length=length):
                with self.assertRaises(OSError):
                    subject._require_buffer_range(
                        buffer, 16, pointer, length, ctypes
                    )

    @unittest.skipUnless(os.name == "nt", "Windows VERSIONINFO smoke test")
    def test_reads_real_installed_chrome_version_info(self) -> None:
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if not chrome.is_file():
            self.skipTest("system Chrome is not installed at the standard path")
        info = read_windows_file_version(chrome)
        self.assertEqual("Google Chrome", info.product_name)
        self.assertEqual(4, len(info.file_version))
        self.assertTrue(all(0 <= part <= 0xFFFF for part in info.file_version))


if __name__ == "__main__":
    unittest.main()
