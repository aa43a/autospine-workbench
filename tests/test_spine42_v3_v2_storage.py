"""Immutable publication and exact replay for P10.7a v2."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_files_v2 import NAMESPACE  # noqa: E402
from autospine_workbench.spine42_v3_bundle_reader_v2 import (  # noqa: E402
    VerifiedSpine42V3BundleReaderV2,
    VerifiedSpine42V3BundleReaderV2Error,
    VerifiedSpine42V3BundleV2,
)
from autospine_workbench.spine42_v3_bundle_store_v2 import (  # noqa: E402
    Spine42V3BundleStoreV2,
    Spine42V3BundleStoreV2Error,
)
from autospine_workbench.spine42_v3_export_evidence_v2 import (  # noqa: E402
    AUTHORITY,
    BUNDLE_INVENTORY,
)
from autospine_workbench.spine42_v3_pipeline_v2 import (  # noqa: E402
    VerifiedSpine42V3PipelineV2,
)
from autospine_workbench.p10_spine42_v3_commands_v2 import (  # noqa: E402
    compile_body_sway_spine42_v3_v2_command,
    compile_verified_body_sway_spine42_v3_v2_command,
    verify_body_sway_spine42_v3_v2_command,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402


HEADS = (
    "autospine_workbench.spine42_v3_current_heads_v2."
    "require_current_body_sway_dynamic_seam_heads_v2"
)


class Spine42V3V2StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Spine42V3V2Fixture(Path(self.temporary.name))
        with self.fixture.pipeline_sources():
            self.compilation = VerifiedSpine42V3PipelineV2(
                self.fixture.state_root
            ).build(
                self.fixture.motion_bundle.project_id,
                self.fixture.motion_bundle.motion_instance_v3_sha256,
                self.fixture.motion_bundle.bundle_sha256,
            )

    def tearDown(self):
        self.temporary.cleanup()

    def publish(self, *, observations=None):
        observation = self.fixture.motion_fixture.observation
        values = observations or (observation, observation)
        with patch(HEADS, side_effect=values):
            return Spine42V3BundleStoreV2(
                self.fixture.motion_fixture.capture,
                self.fixture.motion_fixture.project_store,
            ).publish(
                self.compilation, self.fixture.motion_bundle, observation,
            )

    def test_store_reader_reuse_and_namespace_are_exact(self):
        first = self.publish()
        second = self.publish()
        with self.fixture.pipeline_sources(), patch(
            HEADS, side_effect=AssertionError("historical head read"),
        ) as heads:
            verified = VerifiedSpine42V3BundleReaderV2(
                self.fixture.state_root
            ).load(
                first.project_id, first.skeleton_json_sha256,
                first.bundle_sha256,
            )
        heads.assert_not_called()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(self.compilation.document_bytes,
                         verified.document_bytes)
        self.assertEqual(self.compilation.contract_identities,
                         verified.contract_identities)
        self.assertEqual(
            (first.path.name, first.path.parent.name,
             first.path.parent.parent.name),
            (first.bundle_sha256, first.skeleton_json_sha256, NAMESPACE),
        )

    def test_run_v2_inventory_and_capability_boundary_are_exact(self):
        verified = self.publish().verified_bundle
        run = verified.run_manifest
        self.assertEqual(2, run["format_version"])
        self.assertEqual(tuple(BUNDLE_INVENTORY), verified.inventory)
        self.assertEqual(dict(AUTHORITY), run["authority"])
        self.assertEqual("blocked", run["release_gate"]["status"])
        self.assertEqual(9, len(run["release_gate"]["reason_codes"]))
        self.assertEqual(
            {"attachment_id", "sha256"},
            set(run["inputs"]["source_images"][0]),
        )
        self.assertNotIn(str(self.fixture.root), json.dumps(run))

    def test_drift_before_publication_writes_no_bundle(self):
        alternate = type(self.fixture.motion_fixture.observation)(
            "f" * 64, "{}",
        )
        contract = self.fixture.contract()
        destination = (
            self.fixture.state_root / "builds" / contract.project_id /
            NAMESPACE / contract.skeleton_json_sha256 / contract.bundle_sha256
        )
        with self.assertRaises(Spine42V3BundleStoreV2Error):
            self.publish(observations=(alternate,))
        self.assertFalse(destination.exists())

    def test_reader_rejects_wrong_addresses_and_extra_inventory(self):
        published = self.publish()
        reader = VerifiedSpine42V3BundleReaderV2(self.fixture.state_root)
        with self.assertRaises(VerifiedSpine42V3BundleReaderV2Error):
            reader.load(
                published.project_id, "0" * 64, published.bundle_sha256,
            )
        extra = published.path / "extra.json"
        extra.write_bytes(b"{}")
        try:
            with self.assertRaises(VerifiedSpine42V3BundleReaderV2Error):
                reader.load(
                    published.project_id, published.skeleton_json_sha256,
                    published.bundle_sha256,
                )
        finally:
            extra.unlink()

    def test_reader_issuer_receipt_is_not_module_global(self):
        module = sys.modules[VerifiedSpine42V3BundleV2.__module__]
        self.assertFalse(any("receipt" in name.casefold()
                             for name in vars(module)))
        parameters = inspect.signature(VerifiedSpine42V3BundleV2).parameters
        values = []
        for name, parameter in parameters.items():
            if name == "path":
                values.append(Path("issued-only"))
            elif name in {"project_id", "clip_id"}:
                values.append("token")
            elif name in {"_source_images", "_documents"}:
                values.append(())
            elif name != "_verification_receipt" \
                    and parameter.default is inspect.Parameter.empty:
                values.append("0" * 64)
        with self.assertRaises(VerifiedSpine42V3BundleReaderV2Error):
            VerifiedSpine42V3BundleV2(*values)

    def test_commands_compile_and_historically_verify_exact_result(self):
        admission = self.fixture.motion_bundle.document(
            "body-sway-motion-consumer-admission-v2.json"
        )
        source = admission["source"][
            "body_sway_dynamic_seam_probe_v2"
        ]["source"]
        with self.fixture.pipeline_sources(), patch(
            "autospine_workbench.p10_spine42_v3_commands_v2."
            "load_motion_instance_v3_v2_and_dynamic_source",
            return_value=(self.fixture.motion_bundle, source),
        ) as source_load, patch(
            "autospine_workbench.spine42_v3_pipeline_v2."
            "VerifiedSpine42V3PipelineV2.build",
            side_effect=AssertionError("P10.6b source read twice"),
        ), patch(HEADS, return_value=self.fixture.motion_fixture.observation):
            compiled = compile_body_sway_spine42_v3_v2_command(
                self.fixture.motion_fixture.capture,
                self.fixture.motion_fixture.project_store,
                self.fixture.motion_bundle.project_id,
                motion_instance_v3_sha256=(
                    self.fixture.motion_bundle.motion_instance_v3_sha256
                ),
                motion_instance_v3_bundle_sha256=(
                    self.fixture.motion_bundle.bundle_sha256
                ),
            )
        source_load.assert_called_once()
        with self.fixture.pipeline_sources(), patch(
            HEADS, side_effect=AssertionError("historical head read"),
        ) as heads:
            verified = verify_body_sway_spine42_v3_v2_command(
                self.fixture.state_root, compiled.project_id,
                skeleton_json_sha256=compiled.skeleton_json_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )
        heads.assert_not_called()
        self.assertEqual("compiled", compiled.mode)
        self.assertEqual("verified", verified.mode)
        self.assertEqual(compiled.document["address"],
                         verified.document["address"])
        self.assertEqual(
            {"status": "passed", "exact_readback": True},
            verified.document["verification"],
        )

    def test_verified_command_keeps_one_reader_issued_source_in_memory(self):
        with self.fixture.pipeline_sources(), patch(
            "autospine_workbench.p10_spine42_v3_commands_v2."
            "load_motion_instance_v3_v2_and_dynamic_source",
            side_effect=AssertionError("P10.6b source replayed again"),
        ) as source_load, patch(
            HEADS, return_value=self.fixture.motion_fixture.observation,
        ):
            result = compile_verified_body_sway_spine42_v3_v2_command(
                self.fixture.motion_fixture.capture,
                self.fixture.motion_fixture.project_store,
                self.fixture.motion_bundle,
            )
        source_load.assert_not_called()
        self.assertEqual("compiled", result.mode)
        self.assertEqual(
            self.fixture.motion_bundle.motion_instance_v3_sha256,
            result.document["source"]["motion_instance_v3_v2"][
                "motion_instance_v3_sha256"
            ],
        )


if __name__ == "__main__":
    unittest.main()
