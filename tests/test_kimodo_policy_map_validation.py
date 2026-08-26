"""Tests for reviewed Kimodo heading/contact interpretation maps."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.camera_model_validation import (  # noqa: E402
    camera_model_sha256,
)
from autospine_workbench.kimodo_npz_map_validation import (  # noqa: E402
    kimodo_npz_map_sha256,
)
from autospine_workbench.kimodo_policy_map_validation import (  # noqa: E402
    KimodoPolicyMapError,
    kimodo_policy_map_sha256,
    require_kimodo_policy_map,
)
from tests.kimodo_npz_helpers import map_document  # noqa: E402
from tests.test_camera_model_validation import camera_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def policy_document(mapping: dict | None = None, camera: dict | None = None) -> dict:
    mapping = mapping or map_document()
    camera = camera or camera_document()
    return {
        "format": "autospine-kimodo-policy-map",
        "format_version": 1,
        "policy_map_id": "kimodo.soma77.front-policy-v1",
        "source": {
            "kimodo_map_sha256": kimodo_npz_map_sha256(mapping),
            "camera_sha256": camera_model_sha256(camera),
        },
        "heading": {
            "source": "global_root_heading",
            "vector_semantics": "character_forward_world",
            "components": [
                {"index": 0, "source_axis": "+X"},
                {"index": 1, "source_axis": "+Z"},
            ],
            "root_joint_name": "Hips",
            "root_local_forward_axis": "+Z",
            "yaw_convention": "atan2_camera_screen_x_over_camera_depth",
            "crosscheck": {
                "policy": "projected_root_forward_angle",
                "maximum_angle_error_deg": 5.0,
            },
        },
        "contact": {
            "status": "mapped",
            "source": "foot_contacts",
            "interval": "half_open",
            "proxies": [
                {
                    "index": row["index"],
                    "limb": row["limb"],
                    "point": row["point"],
                    "proxy_joint_name": (
                        "Left" if row["limb"] == "leg.left" else "Right"
                    ) + {"heel": "Foot", "toe": "ToeBase", "toe_end": "ToeEnd"}[row["point"]],
                    "proxy_quality": {
                        "heel": "ankle-joint-proxy",
                        "toe": "toe-base-joint-proxy",
                        "toe_end": "toe-end-joint-proxy",
                    }[row["point"]],
                }
                for row in mapping["contact"]["channels"]
            ],
        },
    }


class KimodoPolicyMapValidationTests(unittest.TestCase):
    def test_valid_policy_is_deterministic_and_cross_bound(self):
        mapping, camera = map_document(), camera_document()
        value = policy_document(mapping, camera)
        require_kimodo_policy_map(value, kimodo_map=mapping, camera=camera)
        reordered = dict(reversed(list(value.items())))
        self.assertEqual(
            kimodo_policy_map_sha256(value),
            kimodo_policy_map_sha256(reordered),
        )
        self._schema(value)

    def test_rejects_stale_source_and_heading_axes_outside_camera_plane(self):
        mapping, camera = map_document(), camera_document()
        stale = policy_document(mapping, camera)
        stale["source"]["camera_sha256"] = "0" * 64
        with self.assertRaisesRegex(KimodoPolicyMapError, "identity differs"):
            require_kimodo_policy_map(stale, kimodo_map=mapping, camera=camera)

        wrong_axes = policy_document(mapping, camera)
        wrong_axes["heading"]["components"][1]["source_axis"] = "+Y"
        with self.assertRaisesRegex(KimodoPolicyMapError, "lateral and depth"):
            require_kimodo_policy_map(
                wrong_axes, kimodo_map=mapping, camera=camera
            )

    def test_rejects_guessed_or_misordered_contact_proxies(self):
        mapping, camera = map_document(), camera_document()
        wrong = policy_document(mapping, camera)
        wrong["contact"]["proxies"][0]["proxy_joint_name"] = "LeftToeBase"
        with self.assertRaisesRegex(KimodoPolicyMapError, "pinned SOMA77"):
            require_kimodo_policy_map(wrong, kimodo_map=mapping, camera=camera)

        missing = policy_document(mapping, camera)
        missing["contact"]["proxies"].pop()
        with self.assertRaisesRegex(KimodoPolicyMapError, "mapped channels"):
            require_kimodo_policy_map(missing, kimodo_map=mapping, camera=camera)

    def test_contact_unavailable_only_matches_disabled_map(self):
        mapping, camera = map_document(contact_enabled=False), camera_document()
        value = policy_document(map_document(), camera)
        value["source"]["kimodo_map_sha256"] = kimodo_npz_map_sha256(mapping)
        value["contact"] = {
            "status": "unavailable", "reason_code": "map_contact_disabled",
        }
        require_kimodo_policy_map(value, kimodo_map=mapping, camera=camera)

        enabled = map_document()
        value["source"]["kimodo_map_sha256"] = kimodo_npz_map_sha256(enabled)
        with self.assertRaisesRegex(KimodoPolicyMapError, "cannot be unavailable"):
            require_kimodo_policy_map(value, kimodo_map=enabled, camera=camera)

    def test_rejects_extra_fields_bool_tolerance_and_noncanonical_indices(self):
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["heading"]["crosscheck"].update(
                maximum_angle_error_deg=True
            ),
            lambda value: value["heading"]["components"][0].update(index=1),
            lambda value: value["heading"].update(root_local_forward_axis="forward"),
        )
        for mutate in mutations:
            candidate = policy_document()
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                KimodoPolicyMapError
            ):
                require_kimodo_policy_map(candidate)

    def _schema(self, value: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "kimodo-policy-map-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
