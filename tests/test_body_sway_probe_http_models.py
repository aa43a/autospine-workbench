"""P10.2 public projection tests for remediation-only reclassification."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_http_models import (  # noqa: E402
    body_sway_probe_entry,
)


SHA = "a" * 64


class _Address:
    package_id = SHA
    project_id = "fixture-project"

    @staticmethod
    def public_document():
        return {"project_id": "fixture-project", "clip_id": "clip"}


def _evidence():
    return SimpleNamespace(
        candidates=SimpleNamespace(
            document={"features": [{"feature_id": "body_sway"}]},
            sha256=SHA,
        ),
        address=_Address(),
        mesh_bundle=SimpleNamespace(
            rig={"canvas": {"width": 1024, "height": 1024}},
        ),
    )


def _report(*rejected):
    checks = [
        {"check_id": name, "status": "rejected"}
        for name in rejected
    ]
    return SimpleNamespace(
        sha256="b" * 64,
        document={
            "status": "structural_rejected",
            "release_gate": {"status": "blocked", "reason_codes": []},
            "schedule": {"sample_count": 2},
            "checks": checks,
            "summary": {"check_count": len(checks)},
        },
    )


def _dynamic(status="fitted"):
    return SimpleNamespace(
        sha256="c" * 64,
        document={"fit_status": status, "status": "candidate_only"},
    )


class BodySwayProbeHttpModelTests(unittest.TestCase):
    def _entry(self, report, dynamic, rebind=()):
        head = SimpleNamespace(
            decision=None, current_revision=1, decision_sha256="d" * 64,
        )
        with patch(
            "autospine_workbench.body_sway_probe_http_models."
            "classify_body_sway_probe_head",
            return_value="probe_ready",
        ):
            return body_sway_probe_entry(
                _evidence(), head, report=report,
                dynamic_viewport=dynamic, rebind_candidates=rebind,
            )

    def test_only_canvas_rejection_exposes_adjustment_without_rewriting_report(self):
        report = _report("sampled_canvas_containment")
        original = deepcopy(report.document)
        rebind = (SimpleNamespace(
            sha256="e" * 64,
            document={"status": "candidate_only"},
        ),)
        entry = self._entry(report, _dynamic(), rebind)
        self.assertEqual(3, entry["format_version"])
        self.assertEqual("viewport_adjustment_available", entry["status"])
        self.assertEqual("structural_rejected", entry["result"]["status"])
        self.assertEqual(original, entry["technical"]["report"])
        self.assertEqual(
            {"candidate_sha256", "document"},
            set(entry["dynamic_viewport"]),
        )
        self.assertEqual(
            {"candidate_sha256", "document"},
            set(entry["rebind_candidates"][0]),
        )

    def test_other_rejection_or_unfitted_viewport_remains_blocked(self):
        cases = (
            (_report("sampled_canvas_containment", "fk_finite"), _dynamic()),
            (_report("sampled_canvas_containment"), _dynamic("indeterminate")),
        )
        for report, dynamic in cases:
            with self.subTest(checks=report.document["checks"],
                              fit=dynamic.document["fit_status"]):
                entry = self._entry(report, dynamic)
                self.assertEqual("structural_rejected", entry["status"])


if __name__ == "__main__":
    unittest.main()
