"""Pure read-only P10.7b v2 runtime-source bridge tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_v3_bundle_reader_v2 import (  # noqa: E402
    VerifiedSpine42V3BundleReaderV2,
)
from autospine_workbench.spine42_v3_bundle_store_v2 import (  # noqa: E402
    Spine42V3BundleStoreV2,
)
from autospine_workbench.spine42_v3_pipeline_v2 import (  # noqa: E402
    VerifiedSpine42V3PipelineV2,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    Spine42V3RuntimePlanError,
    build_spine42_v3_runtime_plan,
    canonical_spine42_v3_runtime_plan_bytes,
)
from autospine_workbench.spine42_v3_runtime_plan_v2 import (  # noqa: E402
    Spine42V3RuntimePlanV2Error,
    build_spine42_v3_runtime_plan_v2,
    require_spine42_v3_runtime_plan_v2,
    spine42_v3_runtime_plan_sha256_v2,
)
from autospine_workbench.spine42_v3_runtime_profile_v2 import (  # noqa: E402
    ADMISSION_HASH_DOMAIN,
    PLAN_HASH_DOMAIN,
    spine42_v3_runtime_profile_v2,
    spine42_v3_runtime_source_contract_v2,
)
from autospine_workbench.spine42_v3_runtime_source_admission_v2 import (  # noqa: E402
    Spine42V3RuntimeSourceAdmissionV2Error,
    require_spine42_v3_runtime_source_admission_v2,
    spine42_v3_runtime_source_admission_sha256_v2,
)
from autospine_workbench.spine42_v3_runtime_source_bridge_v2 import (  # noqa: E402
    Spine42V3RuntimeSourceBridgeV2Error,
    VerifiedSpine42V3RuntimeSourceBridgeV2,
    VerifiedSpine42V3RuntimeSourceV2,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402
from tests.test_spine42_v3_runtime_plan import _verified as _v1  # noqa: E402


BRIDGE = "autospine_workbench.spine42_v3_runtime_source_bridge_v2."
REQUIRE_HEADS = (
    "autospine_workbench.spine42_v3_current_heads_v2."
    "require_current_body_sway_dynamic_seam_heads_v2"
)
OBSERVE_HEADS = (
    "autospine_workbench.spine42_v3_current_heads_v2."
    "observe_spine42_v3_current_heads_v2"
)


class Spine42V3RuntimeSourceBridgeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3V2Fixture(Path(cls.temporary.name))
        with cls.fixture.pipeline_sources():
            cls.compilation = VerifiedSpine42V3PipelineV2(
                cls.fixture.state_root
            ).build(
                cls.fixture.motion_bundle.project_id,
                cls.fixture.motion_bundle.motion_instance_v3_sha256,
                cls.fixture.motion_bundle.bundle_sha256,
            )
        observation = cls.fixture.motion_fixture.observation
        with patch(REQUIRE_HEADS, return_value=observation):
            cls.published = Spine42V3BundleStoreV2(
                cls.fixture.motion_fixture.capture,
                cls.fixture.motion_fixture.project_store,
            ).publish(cls.compilation, cls.fixture.motion_bundle, observation)
        cls.bundle = cls.published.verified_bundle
        cls.bridge = VerifiedSpine42V3RuntimeSourceBridgeV2(
            cls.fixture.state_root
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_plan_and_admission_are_deterministic_path_free_and_bounded(self):
        first = self.bridge.build_from_verified(self.bundle)
        second = self.bridge.build_from_verified(self.bundle)
        self.assertEqual(first.document_bytes, second.document_bytes)
        plan, admission = first.plan, first.admission
        self.assertEqual(2, plan["format_version"])
        self.assertEqual(2, admission["format_version"])
        self.assertEqual(plan["source"], admission["source"])
        self.assertEqual(first.capture_plan_sha256,
                         spine42_v3_runtime_plan_sha256_v2(plan))
        self.assertEqual(first.admission_sha256,
                         spine42_v3_runtime_source_admission_sha256_v2(
                             admission
                         ))
        self.assertEqual(self.bundle.contract_identities,
                         plan["source"]["spine42_v3_v2"])
        self.assertEqual("setup", plan["cases"][0]["case_id"])
        self.assertEqual(
            len(plan["cases"]) * (2 + len(plan["attachments"])),
            len(plan["artifacts"]),
        )
        serialized = json.dumps(first.document_bytes, default=str)
        self.assertNotIn(str(self.fixture.state_root), serialized)

    def test_admission_grants_no_runtime_raster_or_release_authority(self):
        admission = self.bridge.build_from_verified(self.bundle).admission
        authority = admission["authority"]
        self.assertTrue(authority["p10_7a_v2_exact_replayed"])
        self.assertTrue(authority["bounded_capture_plan_emitted"])
        for name in (
            "official_runtime_loaded", "runtime_equivalence",
            "raster_metrics_computed", "raster_visual_quality",
            "human_visual_reviewed", "persistent_current_head_authority",
            "publishable_spine_timeline", "release_authority",
        ):
            self.assertFalse(authority[name])
        self.assertEqual("blocked", admission["release_gate"]["status"])
        self.assertEqual(
            spine42_v3_runtime_source_contract_v2(),
            admission["source_contract"],
        )
        policy = admission["source_contract"]["version_policy"]
        self.assertEqual({
            "accepts_p10_7a_v1": False,
            "accepts_p10_7a_v2": True,
            "cross_version_coercion": False,
        }, policy)
        self.assertEqual(2, spine42_v3_runtime_profile_v2()["format_version"])

    def test_v1_and_v2_types_are_rejected_in_both_directions(self):
        with self.assertRaises(Spine42V3RuntimePlanV2Error):
            build_spine42_v3_runtime_plan_v2(_v1())
        with self.assertRaises(Spine42V3RuntimePlanError):
            build_spine42_v3_runtime_plan(self.bundle)

    def test_resealed_plan_and_admission_tamper_fail_exact_replay(self):
        result = self.bridge.build_from_verified(self.bundle)
        plan = result.plan
        plan["source"]["project_id"] = "cross-wired"
        plan.pop("capture_plan_sha256")
        plan["capture_plan_sha256"] = canonical_sha256({
            "domain": PLAN_HASH_DOMAIN, **plan,
        })
        self.assertEqual(plan["capture_plan_sha256"],
                         spine42_v3_runtime_plan_sha256_v2(plan))
        with self.assertRaisesRegex(
            Spine42V3RuntimePlanV2Error, "exact source replay"
        ):
            require_spine42_v3_runtime_plan_v2(plan, bundle=self.bundle)

        admission = result.admission
        admission["authority"]["official_runtime_loaded"] = True
        admission.pop("admission_sha256")
        admission["admission_sha256"] = canonical_sha256({
            "domain": ADMISSION_HASH_DOMAIN, **admission,
        })
        self.assertEqual(
            admission["admission_sha256"],
            spine42_v3_runtime_source_admission_sha256_v2(admission),
        )
        with self.assertRaisesRegex(
            Spine42V3RuntimeSourceAdmissionV2Error, "exact replay"
        ):
            require_spine42_v3_runtime_source_admission_v2(
                admission, bundle=self.bundle, plan=result.plan,
            )

    def test_explicit_address_uses_one_exact_reader_and_no_current_heads(self):
        reader = VerifiedSpine42V3BundleReaderV2(self.fixture.state_root)
        exact_load = Mock(wraps=reader.load)
        with self.fixture.pipeline_sources(), patch(
            BRIDGE + "VerifiedSpine42V3BundleReaderV2",
            return_value=SimpleNamespace(load=exact_load),
        ), patch(
            REQUIRE_HEADS, side_effect=AssertionError("historical head read")
        ) as require_heads, patch(
            OBSERVE_HEADS, side_effect=AssertionError("historical head read")
        ) as observe_heads:
            built = self.bridge.build(
                self.published.project_id,
                self.published.skeleton_json_sha256,
                self.published.bundle_sha256,
            )
        exact_load.assert_called_once_with(
            self.published.project_id,
            self.published.skeleton_json_sha256,
            self.published.bundle_sha256,
        )
        require_heads.assert_not_called()
        observe_heads.assert_not_called()
        self.assertEqual(self.bundle.bundle_sha256,
                         built.spine42_v3_bundle_sha256)

    def test_upstream_byte_tamper_and_forged_bridge_value_are_rejected(self):
        path = self.published.path / "run-manifest.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        try:
            with self.fixture.pipeline_sources(), self.assertRaisesRegex(
                Spine42V3RuntimeSourceBridgeV2Error,
                "runtime source build failed",
            ):
                self.bridge.build(
                    self.published.project_id,
                    self.published.skeleton_json_sha256,
                    self.published.bundle_sha256,
                )
        finally:
            path.write_bytes(original)

        parameters = inspect.signature(
            VerifiedSpine42V3RuntimeSourceV2
        ).parameters
        module = sys.modules[VerifiedSpine42V3RuntimeSourceV2.__module__]
        self.assertFalse(any(
            "receipt" in name.casefold() or "token" in name.casefold()
            for name in vars(module)
        ))
        values = []
        for name, parameter in parameters.items():
            if name in {"_plan_bytes", "_admission_bytes"}:
                values.append(b"{}")
            elif name != "_verification_receipt" \
                    and parameter.default is inspect.Parameter.empty:
                values.append("token" if name in {"project_id", "clip_id"}
                              else "0" * 64)
        with self.assertRaises(Spine42V3RuntimeSourceBridgeV2Error):
            VerifiedSpine42V3RuntimeSourceV2(*values)

    def test_frozen_v1_plan_literal_survives_shared_semantics_refactor(self):
        plan = build_spine42_v3_runtime_plan(_v1())
        canonical = canonical_spine42_v3_runtime_plan_bytes(plan)
        self.assertEqual(
            "4eaa2872eb9f0d1fa667382af02e622bee3e4f297d246430589188af6674d267",
            plan["capture_plan_sha256"],
        )
        self.assertEqual(
            "4f39b48adde23e9ed87b8e82640dd28fd3ba1e2c52998a0fecac1f822a194c73",
            hashlib.sha256(canonical).hexdigest(),
        )

    def test_bridge_output_is_immutable_and_historical_replay_is_exact(self):
        expected = self.bridge.build_from_verified(self.bundle)
        with self.assertRaises(Spine42V3RuntimeSourceBridgeV2Error):
            replace(expected, admission_sha256="0" * 64)
        with self.fixture.pipeline_sources(), patch(
            REQUIRE_HEADS, side_effect=AssertionError("historical head read")
        ) as require_heads, patch(
            OBSERVE_HEADS, side_effect=AssertionError("historical head read")
        ) as observe_heads:
            rebuilt = self.bridge.rebuild_and_verify(expected)
        require_heads.assert_not_called()
        observe_heads.assert_not_called()
        self.assertEqual(expected.document_bytes, rebuilt.document_bytes)


if __name__ == "__main__":
    unittest.main()
