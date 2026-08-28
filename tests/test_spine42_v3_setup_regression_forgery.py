"""Forgery regression tests for the P10.7c replay boundary."""

from __future__ import annotations

from copy import deepcopy
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

from autospine_workbench.spine42_v3_setup_regression_binding import (
    Spine42V3SetupRegressionBindingError,
    require_spine42_v3_setup_regression_report_binding,
)
from autospine_workbench.spine42_v3_setup_regression_report import (
    Spine42V3SetupRegressionReportError,
    build_spine42_v3_setup_regression_report,
    require_spine42_v3_setup_regression_report,
    setup_regression_report_sha256,
)
from autospine_workbench.spine42_v3_setup_regression_sample import (
    setup_regression_sample_sha256,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    decode_rgba_png,
    encode_rgba_png,
)
from autospine_workbench.spine42_v3_raster_metrics import (  # noqa: E402
    compute_spine42_v3_raster_metrics,
)
from autospine_workbench.spine42_v3_runtime_bundle import (  # noqa: E402
    build_spine42_v3_runtime_bundle,
    replay_runtime_evidence,
)
from autospine_workbench.spine42_v3_runtime_evidence import (  # noqa: E402
    MAX_MANIFEST_BYTES,
    MAX_METRICS_BYTES,
    artifact_inventory,
    canonical_json_bytes,
)
from autospine_workbench.spine42_v3_runtime_reader import (  # noqa: E402
    VerifiedSpine42V3RuntimeEvidence,
)
from tests import test_spine42_v3_setup_regression as fixtures
from tests.test_spine42_v3_runtime_evidence_store import _captures, _reports


def fixture():
    case = fixtures.Spine42V3SetupRegressionTests()
    png, p6_raw, _golden_raw, request, golden = case.inputs()
    _request, replayed = case.compare()
    report = build_spine42_v3_setup_regression_report(request, [replayed])
    evidence = (
        json.loads(p6_raw), golden,
        {request["samples"][0]["approved_runtime_case_id"]: png},
        [fixtures.verified_inputs()],
    )
    return request, report, evidence


def require_bound(report, request, evidence):
    with patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "replay_verified_spine42_bundle"
    ), patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "replay_verified_spine42_v3_bundle"
    ), patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "build_spine42_v3_runtime_plan", return_value=fixtures._plan(),
    ):
        return require_spine42_v3_setup_regression_report_binding(
            report, request, *evidence
        )


def rehash(report, *, sample=True):
    if sample:
        row = report["samples"][0]
        row["comparison_sha256"] = setup_regression_sample_sha256(row)
    report["setup_regression_report_sha256"] = \
        setup_regression_report_sha256(report)


class Spine42V3SetupRegressionForgeryTests(unittest.TestCase):
    def test_rehashed_sample_forgery_is_rejected_by_replay_binding(self):
        mutations = (
            ("request-bound-p3", False, lambda row: row["source"].__setitem__(
                "p3_rig_sha256", "f" * 64
            )),
            ("replay-bound-png", True, lambda row: row["actual"].__setitem__(
                "png_sha256", "f" * 64
            )),
            ("replay-bound-threshold", True, lambda row: row["thresholds"].__setitem__(
                "max_channel_delta", 1
            )),
        )
        for label, structurally_valid, mutate in mutations:
            with self.subTest(mutation=label):
                request, original, evidence = fixture()
                forged = deepcopy(original)
                mutate(forged["samples"][0])
                rehash(forged)
                if structurally_valid:
                    require_spine42_v3_setup_regression_report(
                        forged, request
                    )
                else:
                    with self.assertRaises(
                        Spine42V3SetupRegressionReportError
                    ):
                        require_spine42_v3_setup_regression_report(
                            forged, request
                        )
                with self.assertRaises((
                    Spine42V3SetupRegressionBindingError,
                    Spine42V3SetupRegressionReportError,
                )):
                    require_bound(forged, request, evidence)

    def test_rehashed_bool_integer_aliases_are_rejected(self):
        mutations = (
            lambda row: row["summary"].__setitem__("sample_count", True),
            lambda row: row["semantics"].__setitem__(
                "current_head_discovery", 0
            ),
            lambda row: row["capture"].__setitem__(
                "device_pixel_ratio", True
            ),
            lambda row: row["authority"].__setitem__("release", 0),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                request, original, _evidence = fixture()
                forged = deepcopy(original)
                mutate(forged)
                rehash(forged, sample=False)
                with self.assertRaises(Spine42V3SetupRegressionReportError):
                    require_spine42_v3_setup_regression_report(forged, request)

    def test_report_samples_cannot_be_supplied_as_replay_sources(self):
        request, report, evidence = fixture()
        approval, golden, approved_pngs, _sources = evidence
        with self.assertRaises(Spine42V3SetupRegressionBindingError):
            require_spine42_v3_setup_regression_report_binding(
                report, request, approval, golden,
                approved_pngs, report["samples"],
            )
        self.assertEqual(report, require_bound(report, request, evidence))

    def test_runtime_wrapper_must_match_rebuilt_evidence_bundle(self):
        plan = fixtures._plan()
        captures = _captures(plan)
        image = decode_rgba_png(captures["case-000.opaque"])
        pixels = bytearray(image.pixels)
        pixels[0] ^= 1
        captures["case-000.opaque"] = encode_rgba_png(RgbaImage(
            image.width, image.height, bytes(pixels)
        ))
        metrics = compute_spine42_v3_raster_metrics(plan, captures)
        manifest = fixtures._evidence().manifest
        manifest["source"]["raster_metrics_sha256"] = \
            metrics["raster_metrics_sha256"]
        manifest["reports"] = _reports(plan, captures)
        manifest["artifacts"] = artifact_inventory(plan, captures)
        changed = replay_runtime_evidence(
            canonical_json_bytes(manifest, MAX_MANIFEST_BYTES, "manifest"),
            canonical_json_bytes(metrics, MAX_METRICS_BYTES, "metrics"),
            tuple(captures.items()),
        )
        old = fixtures._evidence()
        old_bundle = build_spine42_v3_runtime_bundle(old)
        self.assertNotEqual(
            old_bundle.bundle_sha256,
            build_spine42_v3_runtime_bundle(changed).bundle_sha256,
        )
        forged = VerifiedSpine42V3RuntimeEvidence(
            Path("unused"), changed, old_bundle
        )
        approved = captures["case-000.opaque"]
        _png, p6_raw, _golden_raw, request, golden = \
            fixtures.Spine42V3SetupRegressionTests().inputs(approved)
        p6_bundle, spine, _runtime = fixtures.verified_inputs()
        with fixtures.patched_sources(), self.assertRaises(
            fixtures.Spine42V3SetupRegressionError
        ) as caught:
            fixtures.compare_spine42_v3_setup_sample(
                request["samples"][0], json.loads(p6_raw), golden,
                approved, p6_bundle, spine, forged,
            )
        self.assertIn(
            "wrapper differs from exact evidence replay",
            str(caught.exception.__cause__),
        )


if __name__ == "__main__":
    unittest.main()
