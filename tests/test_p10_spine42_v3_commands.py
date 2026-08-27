"""P10.7a compile ordering, authority, drift, and historical replay tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.p10_spine42_v3_commands as module  # noqa: E402
from autospine_workbench.p10_spine42_v3_commands import (  # noqa: E402
    P10Spine42V3CommandError,
    compile_body_sway_spine42_v3_command,
    verify_body_sway_spine42_v3_command,
)
from tests.spine42_v3_storage_helpers import (  # noqa: E402
    Spine42V3StorageFixture,
)


class P10Spine42V3CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3StorageFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, *, observations=None):
        source = self.fixture.published_v3
        with self.fixture.compile_gate(observations=observations):
            return compile_body_sway_spine42_v3_command(
                self.fixture.state_root,
                self.fixture.project_id,
                motion_instance_v3_sha256=
                    source.motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256=source.bundle_sha256,
            )

    def test_compile_and_historical_verify_are_path_free(self):
        compiled = self.compile()
        document = compiled.document
        self.assertEqual("compiled", compiled.mode)
        self.assertTrue(document["authority"]["spine_adapter_emitted"])
        self.assertFalse(document["authority"]["official_runtime_loaded"])
        self.assertFalse(document["head_check"][
            "permanent_authority_claimed"
        ])
        self.assertNotIn(str(self.fixture.root), json.dumps(document))
        detached = compiled.document
        detached["authority"]["release_authority"] = True
        self.assertFalse(compiled.document["authority"]["release_authority"])
        with self.fixture.replay_gate(), patch(
            "autospine_workbench.spine42_v3_current_heads."
            "require_current_body_sway_dynamic_seam_heads",
            side_effect=AssertionError("historical head check attempted"),
        ) as heads:
            verified = verify_body_sway_spine42_v3_command(
                self.fixture.state_root,
                self.fixture.project_id,
                skeleton_json_sha256=compiled.skeleton_json_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )
        heads.assert_not_called()
        self.assertEqual("verified", verified.mode)
        self.assertFalse(verified.document["head_check"][
            "current_heads_observed"
        ])
        self.assertIsNone(verified.reused)

    def test_head_drift_prevents_store_publication(self):
        attacks = (
            (
                SimpleNamespace(identity="before", canonical_bytes=b"same"),
                SimpleNamespace(identity="after", canonical_bytes=b"same"),
            ),
            (
                SimpleNamespace(identity="same", canonical_bytes=b"before"),
                SimpleNamespace(identity="same", canonical_bytes=b"after"),
            ),
        )
        for values in attacks:
            with self.subTest(values=values), patch.object(
                module.Spine42V3BundleStore, "publish"
            ) as publish, self.assertRaisesRegex(
                P10Spine42V3CommandError,
                "Spine 4.2 v3 compilation failed",
            ):
                self.compile(observations=values)
            publish.assert_not_called()

    def test_failed_exact_readback_is_a_command_failure(self):
        with patch.object(
            module.VerifiedSpine42V3BundleReader,
            "load",
            return_value=SimpleNamespace(),
        ), self.assertRaises(P10Spine42V3CommandError):
            self.compile()

    def test_wrong_historical_address_is_rejected(self):
        compiled = self.compile()
        with self.assertRaisesRegex(
            P10Spine42V3CommandError,
            "Spine 4.2 v3 verification failed",
        ):
            verify_body_sway_spine42_v3_command(
                self.fixture.state_root,
                self.fixture.project_id,
                skeleton_json_sha256="0" * 64,
                bundle_sha256=compiled.bundle_sha256,
            )


if __name__ == "__main__":
    unittest.main()
