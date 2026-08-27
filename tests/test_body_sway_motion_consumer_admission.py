"""P10.6a exact source, frozen core, head seal, and public replay tests."""

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

from autospine_workbench.body_sway_dynamic_seam_head_checks import (  # noqa: E402
    BodySwayDynamicSeamHeadObservation,
)
from autospine_workbench.body_sway_motion_consumer_admission import (  # noqa: E402
    BodySwayMotionConsumerAdmissionError,
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from autospine_workbench.body_sway_motion_consumer_profile import (  # noqa: E402
    body_sway_base_channels_sha256,
    body_sway_motion_consumer_source_sha256,
    body_sway_motion_domain_sha256,
)
from autospine_workbench.body_sway_motion_consumer_validation import (  # noqa: E402
    BodySwayMotionConsumerAdmissionValidationError,
    body_sway_motion_consumer_admission_canonical_bytes,
    body_sway_motion_consumer_admission_sha256,
    require_body_sway_motion_consumer_admission,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    consumer_fixture,
    head_observation,
    patched_probe_replay,
)


VALIDATION = "autospine_workbench.body_sway_motion_consumer_validation."


class BodySwayMotionConsumerAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture, cls.bundle, cls.probe, cls.identity = consumer_fixture(
            Path(cls.temporary.name)
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile_core(self, probe=None):
        value = self.probe if probe is None else probe
        with patched_probe_replay(value, self.identity):
            return compile_body_sway_motion_consumer_admission_core(
                value, self.bundle
            )

    def admission(self):
        with patched_probe_replay(self.probe, self.identity):
            core = compile_body_sway_motion_consumer_admission_core(
                self.probe, self.bundle
            )
            observation = head_observation(self.identity)
            return seal_body_sway_motion_consumer_admission(
                core, observation, observation
            )

    def test_core_binds_full_probe_p9_and_exact_unit_gain_domain(self):
        core = self.compile_core()
        document = core.document
        source = document["source"]
        domain = document["motion_domain"]
        motion = self.bundle.document("motion-instance-v2.json")
        self.assertEqual(self.probe, source["body_sway_dynamic_seam_probe"])
        self.assertEqual(self.bundle.identities, source["p9"])
        self.assertEqual(
            body_sway_motion_consumer_source_sha256(source),
            source["source_set_sha256"],
        )
        self.assertEqual({"numerator": 1, "denominator": 1}, domain[
            "selected_gain"
        ])
        self.assertEqual("sampled-linear", domain["rotation_timeline"][
            "interpolation"
        ])
        self.assertEqual(motion["timing"], domain["timing"])
        self.assertEqual(motion["markers"], domain["base_channels"][
            "markers"
        ]["items"])
        self.assertEqual(motion["draw_order"], domain["base_channels"][
            "draw_order"
        ]["value"])
        roots = [track for track in motion["tracks"]
                 if track["property"] == "translation"]
        self.assertEqual(roots, domain["base_channels"][
            "root_translation"
        ]["tracks"])
        self.assertEqual(
            body_sway_base_channels_sha256(domain["base_channels"]),
            domain["base_channels"]["base_channels_sha256"],
        )
        self.assertEqual(
            body_sway_motion_domain_sha256(domain),
            domain["motion_domain_sha256"],
        )

    def test_compile_calls_public_probe_replay_and_head_extraction(self):
        with patched_probe_replay(
            self.probe, self.identity
        ) as (replay, head, _validation):
            compile_body_sway_motion_consumer_admission_core(
                self.probe, self.bundle
            )
        replay.assert_called_once_with(self.probe)
        head.assert_called_once()

    def test_uncertified_or_cross_wired_inputs_fail_closed(self):
        attacks = []
        seam = deepcopy(self.probe)
        seam["status"] = "indeterminate"
        attacks.append(seam)
        proof = deepcopy(self.probe)
        proof["source"]["body_sway_continuous_preview_proof"][
            "status"
        ] = "indeterminate"
        attacks.append(proof)
        p9 = deepcopy(self.probe)
        p9["source"]["body_sway_continuous_preview_proof"]["source"] \
            ["amplitude_envelope_candidate"]["source"] \
            ["reviewed_probe_report"]["source"]["p9"][
                "bundle_sha256"
            ] = "0" * 64
        attacks.append(p9)
        for index, attack in enumerate(attacks):
            with self.subTest(attack=index), patched_probe_replay(
                attack, self.identity
            ), self.assertRaises(BodySwayMotionConsumerAdmissionError):
                compile_body_sway_motion_consumer_admission_core(
                    attack, self.bundle
                )

    def test_verified_bundle_bytes_are_rechecked_not_trusted_by_type_alone(self):
        items = list(self.bundle._document_items)
        name, data = items[4]
        items[4] = (name, data + b"\n")
        spoofed = replace(self.bundle, _document_items=tuple(items))
        with patched_probe_replay(
            self.probe, self.identity
        ), self.assertRaises(BodySwayMotionConsumerAdmissionError):
            compile_body_sway_motion_consumer_admission_core(
                self.probe, spoofed
            )
        with patched_probe_replay(
            self.probe, self.identity
        ), self.assertRaises(BodySwayMotionConsumerAdmissionError):
            compile_body_sway_motion_consumer_admission_core(
                self.probe, object()
            )

    def test_core_is_deterministic_copy_isolated_frozen_and_zero_write(self):
        with patched_probe_replay(self.probe, self.identity), patch(
            "builtins.open", side_effect=AssertionError("write attempted")
        ):
            first = compile_body_sway_motion_consumer_admission_core(
                self.probe, self.bundle
            )
            second = compile_body_sway_motion_consumer_admission_core(
                self.probe, self.bundle
            )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        detached = first.document
        detached["status"] = "forged"
        self.assertNotEqual("forged", first.document["status"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"

    def test_seal_requires_equal_exact_observations_and_keeps_narrow_claims(self):
        core = self.compile_core()
        observation = head_observation(self.identity)
        admission = seal_body_sway_motion_consumer_admission(
            core, observation, observation
        )
        document = admission.document
        self.assertEqual(
            "setup_local_timeline_compilation_admitted", document["status"]
        )
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertTrue(document["claims"][
            "setup_local_timeline_compilation_admitted"
        ])
        for field in (
            "dynamic_seam_safety", "full_attachment_boundary_continuity",
            "raster_visual_quality", "runtime_equivalence",
            "motion_instance_v3_emitted", "spine_adapter_emitted",
            "publishable_timeline", "release_authority",
        ):
            self.assertFalse(document["claims"][field])
        self.assertEqual(2, document["summary"]["head_observation_count"])
        self.assertEqual(admission.sha256, hashlib.sha256(
            admission.canonical_bytes
        ).hexdigest())

    def test_seal_rejects_changed_identity_or_observation_bytes(self):
        core = self.compile_core()
        before = head_observation(self.identity)
        changed_identity = replace(self.identity, visual_revision=8)
        after = head_observation(changed_identity)
        with self.assertRaises(BodySwayMotionConsumerAdmissionError):
            seal_body_sway_motion_consumer_admission(core, before, after)
        forged = BodySwayDynamicSeamHeadObservation(
            self.identity,
            before.canonical_bytes.decode("utf-8")[:-1] + ',"extra":true}',
        )
        with self.assertRaises(BodySwayMotionConsumerAdmissionError):
            seal_body_sway_motion_consumer_admission(core, before, forged)

    def test_public_validator_replays_embedded_probe_core_and_head_seal(self):
        admission = self.admission()
        with patched_probe_replay(
            self.probe, self.identity
        ) as (source_replay, _head, validation_replay):
            self.assertIsNone(require_body_sway_motion_consumer_admission(
                admission.document, reviewed_bundle=self.bundle
            ))
            canonical = body_sway_motion_consumer_admission_canonical_bytes(
                admission.document,
                dynamic_seam_probe=self.probe,
                reviewed_bundle=self.bundle,
            )
            digest = body_sway_motion_consumer_admission_sha256(
                admission.document, reviewed_bundle=self.bundle
            )
        self.assertGreaterEqual(source_replay.call_count, 3)
        self.assertGreaterEqual(validation_replay.call_count, 4)
        self.assertEqual(admission.canonical_bytes, canonical)
        self.assertEqual(admission.sha256, digest)

    def test_every_semantic_section_and_external_probe_mismatch_fail(self):
        admission = self.admission().document
        attacks = []
        for path, value in (
            (("claims", "runtime_equivalence"), True),
            (("motion_domain", "selected_gain", "numerator"), 0),
            (("source", "target_profile_sha256"), "0" * 64),
            (("head_observations", "observations_match"), False),
            (("release_gate", "status"), "passed"),
            (("summary", "sample_count"), 999),
        ):
            attack = deepcopy(admission)
            cursor = attack
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            attacks.append(attack)
        for index, attack in enumerate(attacks):
            with self.subTest(attack=index), patched_probe_replay(
                self.probe, self.identity
            ), self.assertRaises(
                BodySwayMotionConsumerAdmissionValidationError
            ):
                require_body_sway_motion_consumer_admission(
                    attack, reviewed_bundle=self.bundle
                )
        other = deepcopy(self.probe)
        other["clip_id"] = "wave"
        with patched_probe_replay(
            self.probe, self.identity
        ), self.assertRaises(BodySwayMotionConsumerAdmissionValidationError):
            require_body_sway_motion_consumer_admission(
                admission, dynamic_seam_probe=other,
                reviewed_bundle=self.bundle,
            )

    def test_nonfinite_and_budget_fail_before_probe_replay(self):
        admission = self.admission().document
        admission["motion_domain"]["rotation_timeline"]["tracks"][0][
            "keys"
        ][0]["value"] = float("nan")
        with patch(
            VALIDATION + "body_sway_dynamic_seam_probe_canonical_bytes"
        ) as replay, self.assertRaises(
            BodySwayMotionConsumerAdmissionValidationError
        ):
            require_body_sway_motion_consumer_admission(
                admission, reviewed_bundle=self.bundle
            )
        replay.assert_not_called()
        valid = self.admission().document
        with patch(
            VALIDATION + "MAX_DOCUMENT_BYTES", 1
        ), patch(
            VALIDATION + "body_sway_dynamic_seam_probe_canonical_bytes"
        ) as replay, self.assertRaisesRegex(
            BodySwayMotionConsumerAdmissionValidationError, "byte limit"
        ):
            require_body_sway_motion_consumer_admission(
                valid, reviewed_bundle=self.bundle
            )
        replay.assert_not_called()

    def test_validation_accessors_are_copy_isolated(self):
        admission = self.admission()
        document = admission.document
        with patched_probe_replay(self.probe, self.identity):
            canonical = body_sway_motion_consumer_admission_canonical_bytes(
                document, reviewed_bundle=self.bundle
            )
        document["source"]["p9"]["bundle_sha256"] = "0" * 64
        self.assertEqual(admission.canonical_bytes, canonical)
        self.assertEqual(
            self.bundle.bundle_sha256,
            admission.document["source"]["p9"]["bundle_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
