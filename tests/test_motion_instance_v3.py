"""P10.6b MotionInstance v3 compiler, replay, and schema tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
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

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.body_sway_motion_consumer_admission import (  # noqa: E402
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from autospine_workbench.motion_instance_v3_compiler import (  # noqa: E402
    MotionInstanceV3CompilerError,
    compile_motion_instance_v3,
)
from autospine_workbench.motion_instance_v3_contract import (  # noqa: E402
    OVERLAY_ROTATION_BONE_IDS,
    motion_instance_v3_profile_sha256,
)
from autospine_workbench.motion_instance_v3_validation import (  # noqa: E402
    MotionInstanceV3ValidationError,
    motion_instance_v3_canonical_bytes,
    motion_instance_v3_sha256,
    require_motion_instance_v3,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    consumer_fixture,
    head_observation,
    patched_probe_replay,
)


class MotionInstanceV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture, cls.bundle, cls.probe, cls.identity = consumer_fixture(
            Path(cls.temporary.name)
        )
        cls.admission = cls._admission_for(cls.probe)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _admission_for(cls, probe):
        with patched_probe_replay(probe, cls.identity):
            core = compile_body_sway_motion_consumer_admission_core(
                probe, cls.bundle
            )
            observation = head_observation(cls.identity)
            return seal_body_sway_motion_consumer_admission(
                core, observation, observation
            )

    def compile(self, admission=None, probe=None):
        admission = admission or self.admission
        probe = probe or self.probe
        with patched_probe_replay(probe, self.identity):
            return compile_motion_instance_v3(
                admission.document, self.bundle
            )

    def validate(self, document, admission=None, probe=None):
        admission = admission or self.admission
        probe = probe or self.probe
        with patched_probe_replay(probe, self.identity):
            return require_motion_instance_v3(
                document,
                admission=admission.document,
                reviewed_bundle=self.bundle,
            )

    def test_compiler_is_deterministic_frozen_copy_isolated_and_zero_write(self):
        with patched_probe_replay(self.probe, self.identity), patch(
            "builtins.open", side_effect=AssertionError("write attempted")
        ):
            first = compile_motion_instance_v3(
                self.admission.document, self.bundle
            )
            second = compile_motion_instance_v3(
                self.admission.document, self.bundle
            )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        detached = first.document
        detached["format_version"] = 99
        self.assertEqual(3, first.document["format_version"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"

    def test_source_profile_and_all_v2_channels_are_bound_exactly(self):
        value = self.compile()
        document = value.document
        admission = self.admission.document
        domain = admission["motion_domain"]
        motion = self.bundle.document("motion-instance-v2.json")
        source = document["source"]
        self.assertEqual(3, document["format_version"])
        self.assertEqual(self.admission.sha256, source[
            "body_sway_motion_consumer_admission_sha256"
        ])
        self.assertEqual({
            "motion_instance_v2_sha256": self.bundle.motion_instance_v2_sha256,
            "bundle_sha256": self.bundle.bundle_sha256,
        }, source["p9"])
        self.assertEqual(domain["motion_domain_sha256"], source[
            "motion_domain_sha256"
        ])
        self.assertEqual(domain["rotation_timeline"][
            "rotation_timeline_sha256"
        ], source["rotation_timeline_sha256"])
        self.assertEqual(domain["base_channels"][
            "base_channels_sha256"
        ], source["base_channels_sha256"])
        self.assertEqual(
            motion_instance_v3_profile_sha256(),
            source["motion_instance_v3_profile_sha256"],
        )
        self.assertEqual("linear", document["target_space"]["interpolation"])
        self.assertEqual("sampled-linear", document["profile"][
            "source_rotation_interpolation"
        ])
        self.assertEqual(motion["markers"], document["markers"])
        self.assertEqual(motion["draw_order"], document["draw_order"])
        roots = [track for track in motion["tracks"]
                 if track["property"] == "translation"]
        self.assertEqual(roots, [track for track in document["tracks"]
                                if track["property"] == "translation"])
        base_rotations = {track["bone_id"] for track in motion["tracks"]
                          if track["property"] == "rotation"}
        output_rotations = {track["bone_id"] for track in document["tracks"]
                            if track["property"] == "rotation"}
        self.assertLessEqual(base_rotations, output_rotations)
        self.assertLessEqual(
            output_rotations - base_rotations,
            set(OVERLAY_ROTATION_BONE_IDS),
        )
        self.assertEqual(
            sorted((track["bone_id"], track["property"])
                   for track in document["tracks"]),
            [(track["bone_id"], track["property"])
             for track in document["tracks"]],
        )

    def test_overlay_fence_accepts_four_bones_only_and_retains_v2_inventory(self):
        allowed_probe = self._probe_with_rotation_delta(
            "pelvis-spine", 2.0
        )
        allowed_admission = self._admission_for(allowed_probe)
        value = self.compile(allowed_admission, allowed_probe)
        pelvis = next(track for track in value.document["tracks"]
                      if track["bone_id"] == "pelvis-spine"
                      and track["property"] == "rotation")
        base = next(track for track in self.bundle.document(
            "motion-instance-v2.json"
        )["tracks"] if track["bone_id"] == "pelvis-spine")
        self.assertEqual(base["keys"][0]["value"] + 2.0,
                         pelvis["keys"][0]["value"])

        non_overlay_probe = self._probe_with_rotation_delta("calf.left", 2.0)
        non_overlay_admission = self._admission_for(non_overlay_probe)
        with patched_probe_replay(
            non_overlay_probe, self.identity
        ), self.assertRaisesRegex(
            MotionInstanceV3CompilerError, "non-overlay"
        ):
            compile_motion_instance_v3(
                non_overlay_admission.document, self.bundle
            )

        dropped_probe = self._probe_without_rotation("forearm.left")
        dropped_admission = self._admission_for(dropped_probe)
        with patched_probe_replay(
            dropped_probe, self.identity
        ), self.assertRaisesRegex(
            MotionInstanceV3CompilerError, "retain every MIv2"
        ):
            compile_motion_instance_v3(dropped_admission.document, self.bundle)

    def test_strict_validator_rejects_shape_and_exact_replay_tampering(self):
        document = self.compile().document
        self.assertIsNone(self.validate(document))
        attacks = []

        unknown = deepcopy(document)
        unknown["latest"] = True
        attacks.append(unknown)

        target_sampling = deepcopy(document)
        target_sampling["target_space"]["interpolation"] = "sampled-linear"
        attacks.append(target_sampling)

        profile = deepcopy(document)
        profile["profile"]["source_rotation_interpolation"] = "linear"
        attacks.append(profile)

        source = deepcopy(document)
        source["source"]["motion_domain_sha256"] = "0" * 64
        attacks.append(source)

        rotation = deepcopy(document)
        track = next(item for item in rotation["tracks"]
                     if item["bone_id"] == "calf.left")
        track["keys"][0]["value"] += 1.0
        track["keys"][-1]["value"] += 1.0
        attacks.append(rotation)

        markers = deepcopy(document)
        markers["markers"].pop()
        attacks.append(markers)

        translation = deepcopy(document)
        root = next(item for item in translation["tracks"]
                    if item["property"] == "translation")
        root["keys"][1]["value"][0] += 1.0
        attacks.append(translation)

        for index, attack in enumerate(attacks):
            with self.subTest(attack=index), self.assertRaises(
                MotionInstanceV3ValidationError
            ):
                self.validate(attack)

    def test_canonical_accessors_replay_exact_sources(self):
        value = self.compile()
        with patched_probe_replay(self.probe, self.identity):
            canonical = motion_instance_v3_canonical_bytes(
                value.document,
                admission=self.admission.document,
                reviewed_bundle=self.bundle,
            )
            digest = motion_instance_v3_sha256(
                value.document,
                admission=self.admission.document,
                reviewed_bundle=self.bundle,
            )
        self.assertEqual(value.canonical_bytes, canonical)
        self.assertEqual(value.sha256, digest)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_v3_and_rejects_v2_or_sampled_target(self):
        schema = json.loads((
            ROOT / "schemas" / "motion-instance-v3.schema.json"
        ).read_text("utf-8"))
        validator = Draft202012Validator(schema)
        document = self.compile().document
        self.assertEqual([], list(validator.iter_errors(document)))
        v2 = self.bundle.document("motion-instance-v2.json")
        self.assertNotEqual([], list(validator.iter_errors(v2)))
        sampled = deepcopy(document)
        sampled["target_space"]["interpolation"] = "sampled-linear"
        self.assertNotEqual([], list(validator.iter_errors(sampled)))

    def _probe_with_rotation_delta(self, bone_id, delta):
        probe = deepcopy(self.probe)
        projection, continuous = self._projection(probe)
        track = next(item for item in projection["rotation_tracks"]
                     if item["bone_id"] == bone_id)
        for key in track["keys"]:
            key["value"] += delta
        continuous["preview_projection_sha256"] = canonical_sha256(projection)
        return probe

    def _probe_without_rotation(self, bone_id):
        probe = deepcopy(self.probe)
        projection, continuous = self._projection(probe)
        projection["rotation_tracks"] = [
            track for track in projection["rotation_tracks"]
            if track["bone_id"] != bone_id
        ]
        count = len(projection["rotation_tracks"])
        projection["summary"].update(
            rotation_track_count=count,
            rotation_key_count=count * len(projection["sample_ticks"]),
        )
        continuous["preview_projection_sha256"] = canonical_sha256(projection)
        return probe

    @staticmethod
    def _projection(probe):
        continuous = probe["source"][
            "body_sway_continuous_preview_proof"
        ]["source"]
        return continuous["preview_projection"], continuous


if __name__ == "__main__":
    unittest.main()
