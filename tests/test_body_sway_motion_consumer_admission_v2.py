"""P10.6a v2 exact source, setup-local core, head seal, and replay tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_head_checks_v2 import (  # noqa: E402
    BodySwayDynamicSeamHeadObservationV2,
)
from autospine_workbench.body_sway_dynamic_seam_bundle_reader_v2 import (  # noqa: E402
    BodySwayDynamicSeamBundleReaderV2Error,
    VerifiedBodySwayDynamicSeamBundleV2,
)
from autospine_workbench.body_sway_motion_consumer_admission_v2 import (  # noqa: E402
    BodySwayMotionConsumerAdmissionV2Error,
    seal_body_sway_motion_consumer_admission_v2,
)
from autospine_workbench.body_sway_motion_consumer_core_v2 import (  # noqa: E402
    compile_body_sway_motion_consumer_admission_core_v2,
)
from autospine_workbench.body_sway_motion_consumer_profile import (  # noqa: E402
    body_sway_motion_consumer_source_sha256,
)
from autospine_workbench.body_sway_motion_consumer_profile_v2 import (  # noqa: E402
    body_sway_base_channels_sha256_v2,
    body_sway_motion_consumer_source_sha256_v2,
    body_sway_motion_domain_sha256_v2,
)
from autospine_workbench.body_sway_motion_consumer_validation_v2 import (  # noqa: E402
    BodySwayMotionConsumerAdmissionV2ValidationError,
    body_sway_motion_consumer_admission_canonical_bytes_v2,
    body_sway_motion_consumer_admission_sha256_v2,
    require_body_sway_motion_consumer_admission_v2,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.body_sway_motion_consumer_v2_helpers import (  # noqa: E402
    consumer_v2_fixture,
    head_observation_v2,
    patched_dynamic_bundle_replay,
)


VALIDATION = "autospine_workbench.body_sway_motion_consumer_validation_v2."
SOURCE = "autospine_workbench.body_sway_motion_consumer_source_v2."


class BodySwayMotionConsumerAdmissionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        (
            cls.fixture, cls.p9, cls.dynamic, cls.dynamic_contract,
        ) = consumer_v2_fixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def core(self, dynamic=None):
        value = self.dynamic if dynamic is None else dynamic
        with patched_dynamic_bundle_replay(value, self.dynamic_contract):
            return compile_body_sway_motion_consumer_admission_core_v2(
                value, self.p9,
            )

    def admission(self):
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ):
            core = compile_body_sway_motion_consumer_admission_core_v2(
                self.dynamic, self.p9,
            )
            head = head_observation_v2(core)
            return seal_body_sway_motion_consumer_admission_v2(
                core, head, head,
            )

    def test_core_binds_exact_v2_bundle_p9_and_setup_local_domain(self):
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ) as rebuilt:
            core = compile_body_sway_motion_consumer_admission_core_v2(
                self.dynamic, self.p9,
            )
        document, motion = core.document, self.p9.document(
            "motion-instance-v2.json"
        )
        source, domain = document["source"], document["motion_domain"]
        self.assertEqual(2, document["format_version"])
        self.assertEqual(self.dynamic.probe, source[
            "body_sway_dynamic_seam_probe_v2"
        ])
        self.assertEqual(self.dynamic.bundle_sha256, source[
            "dynamic_seam_bundle_sha256"
        ])
        self.assertEqual(self.p9.identities, source["p9"])
        self.assertEqual(
            body_sway_motion_consumer_source_sha256_v2(source),
            source["source_set_sha256"],
        )
        self.assertEqual({"numerator": 1, "denominator": 1}, domain[
            "selected_gain"
        ])
        self.assertEqual(motion["target_space"], domain["coordinate_space"])
        self.assertEqual(motion["timing"], domain["timing"])
        self.assertEqual(motion["markers"], domain["base_channels"][
            "markers"
        ]["items"])
        self.assertEqual(motion["draw_order"], domain["base_channels"][
            "draw_order"
        ]["value"])
        self.assertEqual(
            body_sway_base_channels_sha256_v2(domain["base_channels"]),
            domain["base_channels"]["base_channels_sha256"],
        )
        self.assertEqual(
            body_sway_motion_domain_sha256_v2(domain),
            domain["motion_domain_sha256"],
        )
        rebuilt.assert_called_once()

    def test_v2_hash_domain_differs_from_frozen_v1(self):
        value = {"sample": "same"}
        self.assertNotEqual(
            body_sway_motion_consumer_source_sha256(value),
            body_sway_motion_consumer_source_sha256_v2(value),
        )

    def test_core_is_deterministic_frozen_copy_isolated_and_zero_write(self):
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), patch("builtins.open", side_effect=AssertionError("write attempted")):
            first = compile_body_sway_motion_consumer_admission_core_v2(
                self.dynamic, self.p9,
            )
            second = compile_body_sway_motion_consumer_admission_core_v2(
                self.dynamic, self.p9,
            )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        detached = first.document
        detached["status"] = "forged"
        self.assertNotEqual("forged", first.document["status"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"

    def test_exact_dynamic_and_p9_bytes_are_rechecked(self):
        dynamic_items = list(self.dynamic._documents)
        name, data = dynamic_items[0]
        dynamic_items[0] = (name, data + b"\n")
        with self.assertRaises(BodySwayDynamicSeamBundleReaderV2Error):
            replace(self.dynamic, _documents=tuple(dynamic_items))
        spoofed_dynamic = SimpleNamespace(
            **{
                field: getattr(self.dynamic, field) for field in (
                    "path", "project_id", "clip_id", "source_set_sha256",
                    "source_document_sha256", "probe_sha256",
                    "bundle_sha256",
                )
            },
            _documents=tuple(dynamic_items),
        )
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
            compile_body_sway_motion_consumer_admission_core_v2(
                spoofed_dynamic, self.p9,
            )
        wrong_address = SimpleNamespace(
            **{
                field: getattr(self.dynamic, field) for field in (
                    "path", "project_id", "clip_id", "source_set_sha256",
                    "source_document_sha256", "probe_sha256",
                )
            },
            bundle_sha256="0" * 64,
            _documents=self.dynamic._documents,
        )
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
            compile_body_sway_motion_consumer_admission_core_v2(
                wrong_address, self.p9,
            )
        p9_items = list(self.p9._document_items)
        name, data = p9_items[4]
        p9_items[4] = (name, data + b"\n")
        spoofed_p9 = replace(self.p9, _document_items=tuple(p9_items))
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ), self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
            compile_body_sway_motion_consumer_admission_core_v2(
                self.dynamic, spoofed_p9,
            )

    def test_ordinary_code_cannot_construct_a_verified_dynamic_bundle(self):
        from autospine_workbench import (  # noqa: PLC0415
            body_sway_dynamic_seam_bundle_reader_v2 as reader_module,
        )

        self.assertNotIn(
            "_issue_verified_body_sway_dynamic_seam_bundle_v2",
            vars(reader_module),
        )
        self.assertNotIn("_VERIFIED_BUNDLE_RECEIPT_V2", vars(reader_module))
        with self.assertRaises(BodySwayDynamicSeamBundleReaderV2Error):
            VerifiedBodySwayDynamicSeamBundleV2(
                self.dynamic.path, self.dynamic.project_id,
                self.dynamic.clip_id, self.dynamic.source_set_sha256,
                self.dynamic.source_document_sha256,
                self.dynamic.probe_sha256, self.dynamic.bundle_sha256,
                self.dynamic._documents,
            )

    def test_uncertified_and_cross_wired_values_fail_closed(self):
        attacks = []
        probe = self.dynamic.probe
        probe["status"] = "indeterminate"
        attacks.append((probe, self.dynamic.source))
        source = self.dynamic.source
        source["body_sway_continuous_preview_proof_v2"]["source"][
            "motion_instance_v2_sha256"
        ] = "0" * 64
        attacks.append((deepcopy(self.dynamic.probe), source))
        for index, (probe_value, source_value) in enumerate(attacks):
            with self.subTest(index=index), patch(
                SOURCE + "require_exact_body_sway_dynamic_seam_bundle_v2",
                return_value=(source_value, probe_value),
            ), self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
                compile_body_sway_motion_consumer_admission_core_v2(
                    self.dynamic, self.p9,
                )

    def test_seal_accepts_only_equal_exact_v2_observations(self):
        core = self.core()
        head = head_observation_v2(core)
        admission = seal_body_sway_motion_consumer_admission_v2(
            core, head, head,
        )
        document = admission.document
        self.assertEqual(2, document["format_version"])
        self.assertEqual(
            "setup_local_timeline_compilation_admitted", document["status"]
        )
        self.assertTrue(document["claims"][
            "setup_local_timeline_compilation_admitted"
        ])
        for field in (
            "attachment_area_overlap_assessed", "dynamic_seam_safety",
            "raster_visual_quality", "runtime_equivalence",
            "motion_instance_v3_emitted", "spine_adapter_emitted",
            "publishable_timeline", "release_authority",
        ):
            self.assertFalse(document["claims"][field])
        self.assertNotIn("motion_instance_v4", document)
        changed = replace(head, identity_sha256="f" * 64)
        with self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
            seal_body_sway_motion_consumer_admission_v2(core, head, changed)
        forged_doc = head.document
        forged_doc["checks"]["visual_review_v2_head"] = "historical"
        forged = BodySwayDynamicSeamHeadObservationV2(
            head.identity_sha256,
            canonical_json_bytes(forged_doc).decode("utf-8"),
        )
        with self.assertRaises(BodySwayMotionConsumerAdmissionV2Error):
            seal_body_sway_motion_consumer_admission_v2(core, head, forged)

    def test_public_validator_recomputes_every_section_and_identity(self):
        admission = self.admission()
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ):
            self.assertIsNone(require_body_sway_motion_consumer_admission_v2(
                admission.document, dynamic_seam_bundle=self.dynamic,
                reviewed_bundle=self.p9,
            ))
            canonical = body_sway_motion_consumer_admission_canonical_bytes_v2(
                admission.document, dynamic_seam_bundle=self.dynamic,
                reviewed_bundle=self.p9,
            )
            digest = body_sway_motion_consumer_admission_sha256_v2(
                admission.document, dynamic_seam_bundle=self.dynamic,
                reviewed_bundle=self.p9,
            )
        self.assertEqual(admission.canonical_bytes, canonical)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)

        for path, value in (
            (("format_version",), 1),
            (("claims", "runtime_equivalence"), True),
            (("motion_domain", "selected_gain", "numerator"), 0),
            (("source", "dynamic_seam_bundle_sha256"), "0" * 64),
            (("head_observations", "observations_match"), False),
            (("release_gate", "status"), "passed"),
            (("summary", "sample_count"), 999),
        ):
            attack = admission.document
            cursor = attack
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path), patched_dynamic_bundle_replay(
                self.dynamic, self.dynamic_contract,
            ), self.assertRaises(
                BodySwayMotionConsumerAdmissionV2ValidationError
            ):
                require_body_sway_motion_consumer_admission_v2(
                    attack, dynamic_seam_bundle=self.dynamic,
                    reviewed_bundle=self.p9,
                )

    def test_nonfinite_and_budget_fail_before_exact_bundle_replay(self):
        admission = self.admission().document
        admission["motion_domain"]["rotation_timeline"]["tracks"][0][
            "keys"
        ][0]["value"] = float("nan")
        with patch(
            VALIDATION + "compile_body_sway_motion_consumer_admission_core_v2"
        ) as compiler, self.assertRaises(
            BodySwayMotionConsumerAdmissionV2ValidationError
        ):
            require_body_sway_motion_consumer_admission_v2(
                admission, dynamic_seam_bundle=self.dynamic,
                reviewed_bundle=self.p9,
            )
        compiler.assert_not_called()
        valid = self.admission().document
        with patch(VALIDATION + "MAX_DOCUMENT_BYTES", 1), patch(
            VALIDATION + "compile_body_sway_motion_consumer_admission_core_v2"
        ) as compiler, self.assertRaisesRegex(
            BodySwayMotionConsumerAdmissionV2ValidationError, "byte limit"
        ):
            require_body_sway_motion_consumer_admission_v2(
                valid, dynamic_seam_bundle=self.dynamic,
                reviewed_bundle=self.p9,
            )
        compiler.assert_not_called()

if __name__ == "__main__":
    unittest.main()
