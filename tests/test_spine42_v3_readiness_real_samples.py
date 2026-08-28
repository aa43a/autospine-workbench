"""Opt-in zero-write readiness gate for both real See-through samples."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_manifest import (  # noqa: E402
    require_spine42_v3_readiness_request,
)
from autospine_workbench.spine42_v3_readiness_validation import (  # noqa: E402
    require_spine42_v3_readiness_report,
)


ENABLE = os.environ.get("AUTOSPINE_VERIFY_REAL_READINESS") == "1"
GOLDEN = ROOT / "tests" / "goldens" / "p10-seam-anchors" / \
    "real-samples.approved.json"


def _state_root() -> Path:
    value = os.environ.get("AUTOSPINE_REAL_STATE_ROOT")
    return Path(value) if value else ROOT / "workspace"


def _request() -> dict:
    approved = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = [{
        "project_id": sample["project_id"],
        **sample["source"],
        "reviewed_motion_address": None,
        "reviewed_seam_anchor_set_address": None,
        "motion_instance_v3_address": None,
        "spine42_v3_address": None,
        "runtime_capture_address": None,
        "raster_review_decision": None,
    } for sample in approved["samples"]]
    return require_spine42_v3_readiness_request({
        "format": "autospine-spine42-v3-readiness-request",
        "format_version": 1,
        "samples": rows,
    })


def _inventory(root: Path):
    return tuple(
        (
            path.relative_to(root).as_posix(), path.is_dir(),
            0 if path.is_dir() else path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    )


@unittest.skipUnless(ENABLE, "real readiness gate is explicitly enabled")
class Spine42V3ReadinessRealSampleTests(unittest.TestCase):
    def test_exact_dual_sample_blockers_are_deterministic_and_zero_write(self):
        root, request = _state_root(), _request()
        before = _inventory(root)
        first = audit_spine42_v3_readiness(request, root)
        second = audit_spine42_v3_readiness(request, root)
        after = _inventory(root)
        require_spine42_v3_readiness_report(first)
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertEqual("blocked_prerequisites_or_review", first["status"])
        self.assertEqual(
            "5a2258c54c9c6e9465d47dd006a33ae36aea74b85cd61c8b037b3ba686a52396",
            first["readiness_report_sha256"],
        )
        self.assertEqual({
            "metrics_rejected": 0,
            "prerequisite_missing": 13,
            "review_blocked": 1,
            "source_mismatch": 0,
            "verified": 2,
        }, first["summary"]["checkpoint_status_counts"])
        samples = {row["project_id"]: row for row in first["samples"]}
        a, b = samples["seethrough_output"], samples["seethrough_output_5"]
        self.assertEqual(
            "8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6",
            a["checkpoints"][0]["evidence"]["candidate_sha256"],
        )
        self.assertEqual(
            ["reviewed_seam_anchor_set_address_not_declared"],
            a["checkpoints"][2]["reason_codes"],
        )
        self.assertEqual(
            "f53d049df823b2507db5cafa7e0d06bf97519e6bf0494bbfb53c5911d37d2a37",
            b["checkpoints"][0]["evidence"]["candidate_sha256"],
        )
        self.assertEqual(4, b["checkpoints"][2]["evidence"][
            "unobservable_count"
        ])
        self.assertEqual(
            ["seam_relationships_unobservable"],
            b["checkpoints"][2]["reason_codes"],
        )


if __name__ == "__main__":
    unittest.main()
