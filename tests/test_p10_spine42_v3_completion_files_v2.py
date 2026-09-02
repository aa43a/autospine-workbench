from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_job_v2 import (
    NAMESPACE, P10Spine42V3JobStoreV2,
)
from autospine_workbench.spine42_v3_runtime_candidate_catalog_v2 import (
    read_spine42_v3_runtime_candidate_catalog_v2,
)
from tests.p10_spine42_v3_runtime_candidate_support import (
    complete, inputs, tree_snapshot,
)


class P10Spine42V3CompletionFilesV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)
        self.row = complete(self.store, self.store.create(
            inputs(), attempt=1, previous_run_id=None))
        self.run = self.root / "jobs" / NAMESPACE / self.row.run_id

    def tearDown(self):
        self.temporary.cleanup()

    def _assert_rejected_without_write(self):
        before = tree_snapshot(self.root)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual(before, tree_snapshot(self.root))
        self.assertEqual((), catalog.candidates)
        self.assertEqual("invalid_run", catalog.skips[0]["code"])
        self.assertEqual("blocked", catalog.selection["mode"])

    def test_extra_run_root_file_cannot_remain_automatic(self):
        (self.run / "unexpected.bin").write_bytes(b"unexpected")
        self._assert_rejected_without_write()

    def test_wrong_case_fixed_name_is_rejected(self):
        (self.run / "request.json").rename(self.run / "Request.json")
        self._assert_rejected_without_write()

    def test_fixed_entry_with_wrong_type_is_rejected(self):
        request = self.run / "request.json"
        request.unlink()
        request.mkdir()
        self._assert_rejected_without_write()

    def test_aliased_fixed_entry_is_rejected(self):
        request = self.run / "request.json"
        target = self.root / "request-target.json"
        request.rename(target)
        try:
            os.symlink(target, request)
        except (NotImplementedError, OSError):
            self.skipTest("File symlinks are unavailable")
        self._assert_rejected_without_write()


if __name__ == "__main__":
    unittest.main()
