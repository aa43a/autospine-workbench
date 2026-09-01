"""Selected-project Preview v2 current-scope tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_preview_v2_current_scope import (  # noqa: E402
    P10PreviewV2CurrentScopeError, current_p10_preview_v2_scope,
)
from autospine_workbench.p10_preview_v2_service import (  # noqa: E402
    _compile_record, _inventory_sha, _locator,
)
from autospine_workbench.current_project_chain import (  # noqa: E402
    CurrentProjectChain,
)
from tests.test_p10_preview_v2_commands import _PackageFixture  # noqa: E402


class P10PreviewV2CurrentScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = _PackageFixture(Path(cls.temporary.name))
        with cls.fixture.current_chains():
            locator = _locator(cls.fixture.store, cls.fixture.package_id)
            cls.record = _compile_record(cls.fixture.store, locator)
        cls.paths = {
            "layer-a": Path(cls.temporary.name) / "layer-a.png",
            "layer-b": Path(cls.temporary.name) / "layer-b.png",
        }
        cls.paths["layer-a"].write_bytes(b"alpha")
        cls.paths["layer-b"].write_bytes(b"bravo")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_scope_binds_selected_current_source_bytes(self) -> None:
        first = self._scope()
        path = self.paths["layer-a"]
        before, stat = path.read_bytes(), path.stat()
        try:
            path.write_bytes(b"omega")
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            second = self._scope()
        finally:
            path.write_bytes(before)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(self.record.address.project_id, first.project_id)
        self.assertNotEqual(
            first.chain.input_identity_sha256,
            second.chain.input_identity_sha256,
        )

    def test_scope_rejects_resolved_project_drift(self) -> None:
        with self.assertRaisesRegex(
            P10PreviewV2CurrentScopeError, "historical",
        ):
            self._scope(resolved="f" * 64)

    def test_inventory_ignores_unrelated_project_changes(self) -> None:
        project_id = self.record.address.project_id
        chains = {
            **self.fixture.current,
            "unrelated": CurrentProjectChain(
                "unrelated", "a" * 64, "b" * 64, "c" * 64,
            ),
        }
        self.assertEqual(
            self.record.key.inventory_sha256,
            _inventory_sha(
                self.record.key.locator, (project_id, "unrelated"),
                chains, self.record.address, self.record.candidates.sha256,
            ),
        )

    def _scope(self, *, resolved=None):
        p3 = self.record.candidates.document["source"]["p3"]
        project = {
            "id": self.record.address.project_id,
            "resolved": {
                "sha256": resolved or p3["resolved_project_sha256"],
            },
            "layers": [{"id": key} for key in sorted(self.paths)],
        }
        with patch.object(
            self.fixture.store, "get_project", return_value=project,
        ), patch.object(
            self.fixture.store, "resolve_asset",
            side_effect=lambda _project, _kind, layer: self.paths[layer],
        ):
            return current_p10_preview_v2_scope(
                self.fixture.store, self.record,
            )


if __name__ == "__main__":
    unittest.main()
