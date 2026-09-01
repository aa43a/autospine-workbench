"""Lightweight Preview v2 immutable-upstream address tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_preview_v2_service import (  # noqa: E402
    _compile_record, _locator,
)
from autospine_workbench.p10_preview_v2_upstream_address import (  # noqa: E402
    P10PreviewV2UpstreamAddressError,
    require_current_p10_preview_v2_upstreams,
)
from tests.test_p10_preview_v2_commands import _PackageFixture  # noqa: E402


class P10PreviewV2UpstreamAddressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = _PackageFixture(Path(cls.temporary.name))
        with cls.fixture.current_chains():
            locator = _locator(cls.fixture.store, cls.fixture.package_id)
            cls.record = _compile_record(cls.fixture.store, locator)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_exact_p3_and_p5_addresses_are_admitted(self) -> None:
        require_current_p10_preview_v2_upstreams(
            self.fixture.state, self.record,
        )

    def test_changed_p5_byte_is_rejected(self) -> None:
        source = self.record.candidates.document["source"]["p5"]
        path = (
            self.fixture.state / "builds" / self.record.address.project_id
            / "motion-instances" / source["instance_sha256"]
            / source["bundle_sha256"] / "retarget-report.json"
        )
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            with self.assertRaises(P10PreviewV2UpstreamAddressError):
                require_current_p10_preview_v2_upstreams(
                    self.fixture.state, self.record,
                )
        finally:
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
