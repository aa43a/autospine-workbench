"""JSON Schema version and overclaim boundaries for P10.6a v2."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None
    Registry = Resource = None

from autospine_workbench.body_sway_motion_consumer_profile_v2 import (  # noqa: E402
    body_sway_motion_consumer_claims_v2,
    body_sway_motion_consumer_profile_v2,
    body_sway_motion_consumer_release_gate_v2,
)


SHAS = tuple(character * 64 for character in "abcdef0123456789")


def _schema(name):
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _observation():
    identity = {
        "source_set_sha256": SHAS[0],
        "project_id": "fixture-project",
        "visual_review_v2": {
            "admission_sha256": SHAS[1], "candidate_sha256": SHAS[2],
            "revision": 1, "decision_sha256": SHAS[3],
        },
        "seam_anchor_review_v1": {
            "candidate_sha256": SHAS[4], "revision": 2,
            "decision_sha256": SHAS[5], "reviewed_set_sha256": SHAS[6],
        },
    }
    return {
        "method": "visual-v2-recompile-plus-seam-v1-history-replay",
        "scope": "compile_time", "identity_sha256": SHAS[7],
        "identity": identity,
        "checks": {
            "visual_review_v2_head": "observed_current",
            "seam_anchor_review_v1_head": "observed_current",
            "reviewed_seam_anchor_set_v1": "canonical_replay_matched",
        },
        "permanent_authority_claimed": False,
    }


def document():
    observation = _observation()
    observation_sha = hashlib.sha256(json.dumps(
        observation, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    p9 = {
        "foot_lock_candidates_sha256": SHAS[0],
        "depth_order_candidates_sha256": SHAS[1],
        "motion_policy_decision_sha256": SHAS[2],
        "reviewed_motion_policy_sha256": SHAS[3],
        "motion_instance_v2_sha256": SHAS[4],
        "run_sha256": SHAS[5], "bundle_sha256": SHAS[6],
    }
    return {
        "format": "autospine-body-sway-motion-consumer-admission",
        "format_version": 2, "project_id": "fixture-project",
        "clip_id": "idle", "core_sha256": SHAS[8],
        "source": {
            "source_set_sha256": SHAS[0],
            "dynamic_seam_source_set_sha256": SHAS[1],
            "dynamic_seam_source_document_sha256": SHAS[2],
            "dynamic_seam_probe_sha256": SHAS[3],
            "dynamic_seam_bundle_sha256": SHAS[4],
            "body_sway_dynamic_seam_probe_v2": {},
            "body_sway_continuous_preview_proof_v2_sha256": SHAS[5],
            "reviewed_seam_anchor_set_v1_sha256": SHAS[6],
            "reviewed_seam_anchor_set_v1_bundle_sha256": SHAS[7],
            "layer_manifest_sha256": SHAS[8], "p3_rig_sha256": SHAS[9],
            "p3_bundle_sha256": SHAS[10],
            "target_profile_sha256": SHAS[11],
            "preview_projection_v2_sha256": SHAS[12], "p9": p9,
        },
        "motion_domain": {
            "coordinate_space": {}, "timing": {},
            "selected_gain": {"numerator": 1, "denominator": 1},
            "sample_ticks": [0, 1],
            "sample_schedule": {
                "sampling": "p10-preview-v2-probe-schedule",
                "probe_tick_schedule_sha256": SHAS[0],
                "probe_sample_stream_sha256": SHAS[1],
                "sample_count": 2, "first_tick": 0, "last_tick": 1,
            },
            "rotation_timeline": {
                "interpolation": "sampled-linear",
                "projection_v2_sha256": SHAS[2],
                "rotation_timeline_sha256": SHAS[3],
                "tracks": [{"property": "rotation"}],
            },
            "base_channels": {
                "motion_instance_v2_sha256": SHAS[4],
                "root_translation": {
                    "mode": "exact-motion-instance-v2-linear", "tracks": [],
                },
                "markers": {"mode": "exact-motion-instance-v2", "items": []},
                "draw_order": {
                    "mode": "exact-motion-instance-v2-stepped", "value": {},
                },
                "base_channels_sha256": SHAS[5],
            },
            "motion_domain_sha256": SHAS[6],
        },
        "profile": body_sway_motion_consumer_profile_v2(),
        "head_observations": {
            "method": "before-after-current-v2-head-recheck",
            "scope": "compile_time",
            "before": {
                "observation": deepcopy(observation),
                "canonical_sha256": observation_sha,
            },
            "after": {
                "observation": deepcopy(observation),
                "canonical_sha256": observation_sha,
            },
            "observations_match": True,
            "permanent_authority_claimed": False,
            "head_observations_sha256": SHAS[7],
        },
        "claims": body_sway_motion_consumer_claims_v2(),
        "status": "setup_local_timeline_compilation_admitted",
        "release_gate": body_sway_motion_consumer_release_gate_v2(),
        "summary": {
            "sample_count": 2, "rotation_track_count": 1,
            "rotation_key_count": 2, "root_translation_track_count": 0,
            "root_translation_key_count": 0, "marker_count": 0,
            "draw_order_key_count": 1, "head_observation_count": 2,
        },
    }


@unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
class BodySwayMotionConsumerSchemaV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = _schema("body-sway-motion-consumer-admission-v2.schema.json")
        Draft202012Validator.check_schema(cls.schema)
        resources = (
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://autospine.local/schemas/body-sway-dynamic-seam-probe-v2.schema.json",
                "type": "object",
            },
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://autospine.local/schemas/motion-instance-v2.schema.json",
                "$defs": {
                    name: {} for name in (
                        "track", "targetSpace", "timing", "contactMarker",
                        "drawOrder",
                    )
                },
            },
        )
        registry = Registry().with_resources(tuple(
            (item["$id"], Resource.from_contents(item))
            for item in resources
        ))
        cls.validator = Draft202012Validator(cls.schema, registry=registry)

    def test_schema_accepts_exact_v2_outer_contract(self):
        self.validator.validate(document())

    def test_schema_rejects_v1_aliases_and_release_overclaims(self):
        mutations = []
        version = document()
        version["format_version"] = 1
        mutations.append(version)
        file_input = document()
        file_input["source"]["dynamic_seam_probe_path"] = "private.json"
        mutations.append(file_input)
        old_schedule = document()
        old_schedule["motion_domain"]["sample_schedule"]["sampling"] = (
            "p10-probe-schedule"
        )
        mutations.append(old_schedule)
        old_projection = document()
        timeline = old_projection["motion_domain"]["rotation_timeline"]
        timeline["projection_sha256"] = timeline.pop("projection_v2_sha256")
        mutations.append(old_projection)
        overclaim = document()
        overclaim["claims"]["attachment_area_overlap_assessed"] = True
        mutations.append(overclaim)
        stale_head = document()
        stale_head["head_observations"]["scope"] = "permanent"
        mutations.append(stale_head)
        for index, value in enumerate(mutations):
            with self.subTest(index=index):
                self.assertFalse(self.validator.is_valid(value))

    def test_schema_references_only_v2_dynamic_seam_contract(self):
        ref = self.schema["$defs"]["source"]["properties"] \
            ["body_sway_dynamic_seam_probe_v2"]["$ref"]
        self.assertEqual("body-sway-dynamic-seam-probe-v2.schema.json", ref)
        self.assertNotIn(
            "body-sway-dynamic-seam-probe-v1.schema.json",
            json.dumps(self.schema),
        )


if __name__ == "__main__":
    unittest.main()
