"""Pure P10.7b bounded capture-plan contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
)
from autospine_workbench.spine42_v3_bundle_integrity import (  # noqa: E402
    Spine42V3BundleSnapshot,
    verify_spine42_v3_bundle_snapshot,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    Spine42V3RuntimePlanError,
    build_spine42_v3_runtime_plan,
    canonical_spine42_v3_runtime_plan_bytes,
    spine42_v3_runtime_plan_sha256,
)
from autospine_workbench.spine42_v3_runtime_capture_page import (  # noqa: E402
    CAPTURE_CSS_SHA256,
    CAPTURE_JS_SHA256,
)
from autospine_workbench.spine42_v3_runtime_profile import (  # noqa: E402
    MAX_COMPOSITE_CASES,
    MAX_SETUP_ATTACHMENTS,
    TICKS_PER_SECOND,
    spine42_v3_runtime_profile_sha256,
)
from tests.test_spine42_v3_bundle_contract import _build, _inputs  # noqa: E402


def _verified(values=None):
    contract = _build(_inputs() if values is None else values)
    items = tuple(
        (name, contract.document_bytes[name]) for name in DOCUMENT_NAMES
    )
    return verify_spine42_v3_bundle_snapshot(
        Spine42V3BundleSnapshot(Path("detached"), items),
        expected_project_id=contract.project_id,
        expected_skeleton_json_sha256=contract.skeleton_json_sha256,
        expected_bundle_sha256=contract.bundle_sha256,
        require_address_path=False,
    )


def _with_skeleton(bundle, skeleton):
    raw = bundle.document_bytes
    raw[DOCUMENT_NAMES[0]] = json.dumps(
        skeleton, sort_keys=True, separators=(",", ":")
    ).encode()
    return replace(
        bundle,
        _document_items=tuple((name, raw[name]) for name in DOCUMENT_NAMES),
    )


class Spine42V3RuntimePlanTests(unittest.TestCase):
    def test_exact_bundle_builds_deterministic_bounded_inventory(self):
        bundle = _verified()
        first = build_spine42_v3_runtime_plan(bundle)
        second = build_spine42_v3_runtime_plan(bundle)

        self.assertEqual(first, second)
        self.assertEqual(
            first["capture_plan_sha256"],
            spine42_v3_runtime_plan_sha256(first),
        )
        self.assertEqual(
            spine42_v3_runtime_profile_sha256(), first["profile_sha256"]
        )
        self.assertEqual({
            "javascript_sha256": CAPTURE_JS_SHA256,
            "stylesheet_sha256": CAPTURE_CSS_SHA256,
        }, first["harness"])
        arguments = first["browser_execution"]["fixed_arguments"]
        self.assertNotIn("--dump-dom", arguments)
        self.assertFalse(any(
            value.startswith("--virtual-time-budget=") for value in arguments
        ))
        self.assertEqual(
            "collector-terminal",
            first["browser_execution"]["page_lifetime"],
        )
        self.assertEqual(bundle.bundle_sha256, first["source"]["bundle_sha256"])
        self.assertEqual("setup", first["cases"][0]["case_id"])
        self.assertIsNone(first["cases"][0]["animation"])
        self.assertEqual(bundle.clip_id, first["cases"][1]["animation"])
        self.assertEqual(0, first["cases"][1]["tick"])
        self.assertLessEqual(len(first["cases"]), MAX_COMPOSITE_CASES)
        self.assertEqual(2, len(first["attachments"]))
        self.assertEqual(
            len(first["cases"]) * (2 + len(first["attachments"])),
            len(first["artifacts"]),
        )
        self.assertFalse(
            first["sampled_scope"]["continuous_time_safety_claimed"]
        )
        self.assertFalse(first["sampled_scope"]["unsampled_ticks_covered"])

    def test_every_case_names_composites_and_all_setup_isolates(self):
        plan = build_spine42_v3_runtime_plan(_verified())
        rows = {row["artifact_id"]: row for row in plan["artifacts"]}
        expected_pairs = {
            (row["slot_id"], row["attachment_id"])
            for row in plan["attachments"]
        }
        for case in plan["cases"]:
            selected = [rows[item] for item in case["artifact_ids"]]
            self.assertEqual(
                {"opaque_composite", "transparent_composite", "attachment_isolate"},
                {row["kind"] for row in selected},
            )
            self.assertEqual(expected_pairs, {
                (row["slot_id"], row["attachment_id"])
                for row in selected if row["kind"] == "attachment_isolate"
            })
            for row in selected:
                self.assertEqual(f"{row['artifact_id']}.png", row["path"])

    def test_selection_covers_fixed_extrema_boundaries_and_loop_neighbors(self):
        plan = build_spine42_v3_runtime_plan(_verified())
        reasons = {
            reason
            for case in plan["cases"][1:]
            for reason in case["selection_reasons"]
        }
        self.assertTrue({
            "fixed-duration-fraction", "track-global-extremum",
            "track-local-extremum", "event-boundary", "draw-order-boundary",
            "loop-endpoint-neighbor",
        } <= reasons)
        duration = plan["sampled_scope"]["duration_ticks"]
        ticks = plan["sampled_scope"]["sampled_ticks"]
        self.assertTrue({0, 1, duration - 1, duration} <= set(ticks))

    def test_non_grid_key_keeps_original_runtime_time_and_records_error(self):
        values = _inputs()
        animation = values["skeleton_json"]["animations"][values["clip_id"]]
        for timelines in animation["bones"].values():
            for frames in timelines.values():
                frames[1]["time"] = 1 / 3
        plan = build_spine42_v3_runtime_plan(_verified(values))
        selected = [
            case for case in plan["cases"]
            if "track-local-extremum" in case["selection_reasons"]
            and case["time_seconds"] == 1 / 3
        ]
        self.assertTrue(selected)
        self.assertNotEqual(
            selected[0]["time_seconds"],
            selected[0]["tick"] / TICKS_PER_SECOND,
        )
        self.assertGreater(
            plan["sampled_scope"]["max_tick_quantization_error_seconds"], 0
        )

    def test_case_and_attachment_bounds_fail_loud_without_truncation(self):
        values = _inputs()
        animation = values["skeleton_json"]["animations"][values["clip_id"]]
        frame_count = MAX_COMPOSITE_CASES + 4
        for timelines in animation["bones"].values():
            for name, frames in timelines.items():
                if name == "rotate":
                    frames[:] = [{
                        "time": index / (frame_count - 1),
                        "value": float(index % 2),
                    } for index in range(frame_count)]
                else:
                    frames[:] = [{
                        "time": index / (frame_count - 1),
                        "x": float(index % 2), "y": 0.0,
                    } for index in range(frame_count)]
        with self.assertRaisesRegex(Spine42V3RuntimePlanError, "truncated"):
            build_spine42_v3_runtime_plan(_verified(values))

        bundle = _verified()
        skeleton = bundle.skeleton_json
        default = skeleton["skins"][0]["attachments"]
        template_slot = deepcopy(skeleton["slots"][0])
        template_attachment = deepcopy(
            next(iter(default[template_slot["name"]].values()))
        )
        skeleton["slots"] = []
        default.clear()
        for index in range(MAX_SETUP_ATTACHMENTS + 1):
            slot_id, attachment_id = f"slot-{index}", f"attachment-{index}"
            slot = deepcopy(template_slot)
            slot.update(name=slot_id, attachment=attachment_id)
            attachment = deepcopy(template_attachment)
            attachment["path"] = attachment_id
            skeleton["slots"].append(slot)
            default[slot_id] = {attachment_id: attachment}
        forged = _with_skeleton(bundle, skeleton)
        with patch(
            "autospine_workbench.spine42_v3_runtime_plan."
            "replay_verified_spine42_v3_bundle"
        ), self.assertRaisesRegex(
            Spine42V3RuntimePlanError, "attachment count"
        ):
            build_spine42_v3_runtime_plan(forged)

    def test_forged_verified_dataclass_is_replayed_and_rejected(self):
        bundle = _verified()
        skeleton = bundle.skeleton_json
        skeleton["skeleton"]["width"] += 1
        with self.assertRaisesRegex(Spine42V3RuntimePlanError, "replay"):
            build_spine42_v3_runtime_plan(_with_skeleton(bundle, skeleton))

    def test_hash_and_canonical_bytes_reject_tamper_and_nonfinite_values(self):
        plan = build_spine42_v3_runtime_plan(_verified())
        self.assertEqual(
            canonical_spine42_v3_runtime_plan_bytes(plan),
            canonical_spine42_v3_runtime_plan_bytes(deepcopy(plan)),
        )
        plan["source"]["project_id"] = "changed"
        with self.assertRaisesRegex(Spine42V3RuntimePlanError, "digest"):
            spine42_v3_runtime_plan_sha256(plan)
        plan["capture_plan_sha256"] = "0" * 64
        plan["sampled_scope"]["duration_seconds"] = float("nan")
        with self.assertRaisesRegex(Spine42V3RuntimePlanError, "finite JSON"):
            canonical_spine42_v3_runtime_plan_bytes(plan)


if __name__ == "__main__":
    unittest.main()
