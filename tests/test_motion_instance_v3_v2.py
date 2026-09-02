"""P10.6b v2 one-pass preparation, v3 compile, and strict replay tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
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

from autospine_workbench.motion_instance_v3_compiler_v2 import (  # noqa: E402
    MotionInstanceV3V2CompilerError,
    compile_motion_instance_v3_v2,
)
from autospine_workbench.motion_instance_v3_contract import (  # noqa: E402
    OVERLAY_ROTATION_BONE_IDS,
)
from autospine_workbench.motion_instance_v3_contract_v2 import (  # noqa: E402
    MotionInstanceV3V2ContractError,
    build_motion_instance_v3_document_v2,
)
from autospine_workbench.body_sway_motion_consumer_profile_v2 import (  # noqa: E402
    body_sway_motion_domain_sha256_v2,
)
from autospine_workbench.body_sway_preview_projection_v2 import (  # noqa: E402
    body_sway_preview_rotation_timeline_sha256_v2,
)
from autospine_workbench.motion_instance_v3_prepared_v2 import (  # noqa: E402
    MotionInstanceV3PreparedCoreV2,
    MotionInstanceV3PreparedV2Error,
    PreparedMotionInstanceV3V2,
    compile_motion_instance_v3_prepared_core_v2,
    replay_motion_instance_v3_prepared_v2,
    seal_motion_instance_v3_prepared_v2,
)
from autospine_workbench.motion_instance_v3_validation_v2 import (  # noqa: E402
    MotionInstanceV3V2ValidationError,
    motion_instance_v3_canonical_bytes_v2,
    motion_instance_v3_sha256_v2,
    require_motion_instance_v3_v2,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.body_sway_motion_consumer_v2_helpers import (  # noqa: E402
    consumer_v2_fixture,
    head_observation_v2,
    patched_dynamic_bundle_replay,
)


PREPARED_MODULE = "autospine_workbench.motion_instance_v3_prepared_v2."
CHECKS_MODULE = (
    "autospine_workbench.motion_instance_v3_prepared_checks_v2."
)


class MotionInstanceV3V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        (
            cls.fixture, cls.p9, cls.dynamic, cls.dynamic_contract,
        ) = consumer_v2_fixture(Path(cls.temporary.name))
        cls.prepared = cls._prepare()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _prepare(cls):
        with patched_dynamic_bundle_replay(
            cls.dynamic, cls.dynamic_contract,
        ):
            core = compile_motion_instance_v3_prepared_core_v2(
                cls.dynamic, cls.p9,
            )
        head = head_observation_v2(core._consumer_core)
        return seal_motion_instance_v3_prepared_v2(core, head, head)

    def test_compile_is_deterministic_frozen_and_one_pass(self):
        from autospine_workbench import (
            motion_instance_v3_prepared_checks_v2 as checks,
        )

        with patch(
            PREPARED_MODULE + "admit_body_sway_motion_consumer_source_v2",
            wraps=__import__(
                "autospine_workbench.body_sway_motion_consumer_source_v2",
                fromlist=["admit_body_sway_motion_consumer_source_v2"],
            ).admit_body_sway_motion_consumer_source_v2,
        ) as admitted, patch(
            CHECKS_MODULE + "observation_from_document_v2",
            wraps=checks.observation_from_document_v2,
        ) as detached, patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), patch("builtins.open", side_effect=AssertionError("write attempted")):
            core = compile_motion_instance_v3_prepared_core_v2(
                self.dynamic, self.p9,
            )
            head = head_observation_v2(core._consumer_core)
            prepared = seal_motion_instance_v3_prepared_v2(core, head, head)
            first = compile_motion_instance_v3_v2(prepared)
            second = compile_motion_instance_v3_v2(prepared)
            require_motion_instance_v3_v2(first.document, prepared=prepared)
        admitted.assert_called_once()
        self.assertEqual(2, detached.call_count)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        detached = first.document
        detached["format_version"] = 99
        self.assertEqual(3, first.document["format_version"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"

    def test_payload_keeps_exact_base_channels_and_torso_overlay_fence(self):
        document = compile_motion_instance_v3_v2(self.prepared).document
        motion = self.p9.document("motion-instance-v2.json")
        self.assertEqual(3, document["format_version"])
        self.assertEqual(self.prepared.admission_sha256, document["source"][
            "body_sway_motion_consumer_admission_sha256"
        ])
        self.assertEqual(self.prepared.admission["source"][
            "p3_rig_sha256"
        ], document["source"]["rig_ir_sha256"])
        self.assertEqual(motion["markers"], document["markers"])
        self.assertEqual(motion["draw_order"], document["draw_order"])
        roots = [track for track in motion["tracks"]
                 if track["property"] == "translation"]
        self.assertEqual(roots, [track for track in document["tracks"]
                                if track["property"] == "translation"])
        base = {track["bone_id"] for track in motion["tracks"]
                if track["property"] == "rotation"}
        output = {track["bone_id"] for track in document["tracks"]
                  if track["property"] == "rotation"}
        self.assertLessEqual(base, output)
        self.assertLessEqual(output - base, set(OVERLAY_ROTATION_BONE_IDS))

    def test_historical_replay_is_exact_and_rejects_v1_or_tamper(self):
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ):
            replayed = replay_motion_instance_v3_prepared_v2(
                self.prepared.admission, self.dynamic, self.p9,
            )
        self.assertEqual(
            self.prepared.admission_sha256, replayed.admission_sha256,
        )
        for path, value in (
            (("format_version",), 1),
            (("source", "dynamic_seam_bundle_sha256"), "0" * 64),
            (("claims", "motion_instance_v3_emitted"), True),
            (("summary", "sample_count"), 999),
        ):
            attack = self.prepared.admission
            cursor = attack
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path), patched_dynamic_bundle_replay(
                self.dynamic, self.dynamic_contract,
            ), self.assertRaises(MotionInstanceV3PreparedV2Error):
                replay_motion_instance_v3_prepared_v2(
                    attack, self.dynamic, self.p9,
                )

    def test_validator_rejects_payload_and_source_closure_tampering(self):
        document = compile_motion_instance_v3_v2(self.prepared).document
        attacks = []
        source = deepcopy(document)
        source["source"]["rig_ir_sha256"] = "0" * 64
        attacks.append(source)
        marker = deepcopy(document)
        marker["markers"].pop()
        attacks.append(marker)
        draw_order = deepcopy(document)
        draw_order["draw_order"]["keys"] = []
        attacks.append(draw_order)
        rotation = deepcopy(document)
        track = next(item for item in rotation["tracks"]
                     if item["property"] == "rotation")
        track["keys"][0]["value"] += 1.0
        attacks.append(rotation)
        for index, attack in enumerate(attacks):
            with self.subTest(index=index), self.assertRaises(
                MotionInstanceV3V2ValidationError
            ):
                require_motion_instance_v3_v2(
                    attack, prepared=self.prepared,
                )

    def test_contract_rejects_non_torso_rotation_even_with_rehashed_domain(self):
        admission = self.prepared.admission
        domain = admission["motion_domain"]
        timeline = domain["rotation_timeline"]
        track = next(
            item for item in timeline["tracks"]
            if item["bone_id"] not in OVERLAY_ROTATION_BONE_IDS
        )
        track["keys"][0]["value"] += 1.0
        timeline["rotation_timeline_sha256"] = (
            body_sway_preview_rotation_timeline_sha256_v2(
                timeline["tracks"]
            )
        )
        domain["motion_domain_sha256"] = (
            body_sway_motion_domain_sha256_v2(domain)
        )
        with self.assertRaisesRegex(
            MotionInstanceV3V2ContractError, "non-torso"
        ):
            build_motion_instance_v3_document_v2(
                admission, self.prepared.motion_instance_v2,
                admission_sha256=hashlib.sha256(
                    canonical_json_bytes(admission)
                ).hexdigest(),
                p9_bundle_sha256=
                    self.prepared.reviewed_motion_bundle_sha256,
            )

    def test_exact_p9_bytes_are_rechecked_before_preparation(self):
        items = list(self.p9._document_items)
        name, data = items[4]
        items[4] = (name, data + b"\n")
        forged = replace(self.p9, _document_items=tuple(items))
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), self.assertRaises(MotionInstanceV3PreparedV2Error):
            compile_motion_instance_v3_prepared_core_v2(
                self.dynamic, forged,
            )

    def test_canonical_accessors_replay_the_same_v3_bytes(self):
        value = compile_motion_instance_v3_v2(self.prepared)
        canonical = motion_instance_v3_canonical_bytes_v2(
            value.document, prepared=self.prepared,
        )
        digest = motion_instance_v3_sha256_v2(
            value.document, prepared=self.prepared,
        )
        self.assertEqual(value.canonical_bytes, canonical)
        self.assertEqual(value.sha256, digest)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)

    def test_prepared_values_are_factory_issued_not_replaceable(self):
        import autospine_workbench.motion_instance_v3_prepared_v2 as module

        self.assertNotIn("_PREPARED_RECEIPT_V2", vars(module))
        self.assertNotIn("_build_prepared_api", vars(module))
        self.assertFalse(any("issue" in name for name in vars(module)))
        with self.assertRaises(MotionInstanceV3PreparedV2Error):
            PreparedMotionInstanceV3V2(
                self.prepared.project_id, self.prepared.clip_id,
                self.prepared.dynamic_seam_probe_sha256,
                self.prepared.dynamic_seam_bundle_sha256,
                self.prepared.motion_instance_v2_sha256,
                self.prepared.reviewed_motion_bundle_sha256,
                self.prepared.admission_sha256,
                canonical_json_bytes(self.prepared.admission).decode("utf-8"),
                canonical_json_bytes(
                    self.prepared.motion_instance_v2
                ).decode("utf-8"),
            )
        with self.assertRaises(MotionInstanceV3PreparedV2Error):
            replace(self.prepared, admission_sha256="0" * 64)
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ):
            core = compile_motion_instance_v3_prepared_core_v2(
                self.dynamic, self.p9,
            )
        with self.assertRaises(MotionInstanceV3PreparedV2Error):
            MotionInstanceV3PreparedCoreV2(
                core.project_id, core.clip_id,
                core.dynamic_seam_probe_sha256,
                core.dynamic_seam_bundle_sha256,
                core.motion_instance_v2_sha256,
                core.reviewed_motion_bundle_sha256,
                core._consumer_core, core._motion_json,
            )
        with self.assertRaises(MotionInstanceV3PreparedV2Error):
            replace(core, project_id="forged")

    def test_wrong_prepared_type_and_nonfinite_values_fail_closed(self):
        with self.assertRaises(MotionInstanceV3V2CompilerError):
            compile_motion_instance_v3_v2(object())
        document = compile_motion_instance_v3_v2(self.prepared).document
        document["tracks"][0]["keys"][0]["value"] = float("nan")
        with self.assertRaises(MotionInstanceV3V2ValidationError):
            require_motion_instance_v3_v2(document, prepared=self.prepared)


if __name__ == "__main__":
    unittest.main()
