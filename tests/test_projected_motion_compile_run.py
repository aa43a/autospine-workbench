"""Contract tests for reproducible ProjectedMotionIR compile runs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_camera_projection import (  # noqa: E402
    compile_verified_kimodo_projection,
)
from autospine_workbench.projected_motion_compile_run import (  # noqa: E402
    ProjectedMotionCompileRunError,
    build_projected_motion_compile_run,
    require_projected_motion_compile_run,
)
from autospine_workbench.projected_motion_legacy import (  # noqa: E402
    compile_projected_motion_to_motion_ir,
)
from tests.test_kimodo_camera_projection import (  # noqa: E402
    camera_document,
    verified_fixture,
)


def artifacts():
    bundle, mapping = verified_fixture()
    camera = camera_document(mapping)
    projected = compile_verified_kimodo_projection(bundle, camera)
    legacy = compile_projected_motion_to_motion_ir(projected.document)
    return bundle, camera, projected, legacy


class ProjectedMotionCompileRunTests(unittest.TestCase):
    def test_build_is_canonical_deterministic_and_fully_bound(self):
        bundle, camera, projected, legacy = artifacts()
        first = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        )
        second = build_projected_motion_compile_run(
            bundle, deepcopy(camera), projected, deepcopy(legacy)
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, hashlib.sha256(
            first.canonical_bytes
        ).hexdigest())
        self.assertEqual(first.canonical_bytes, json.dumps(
            first.document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
        require_projected_motion_compile_run(
            first.document, camera=camera,
            projected_motion=projected.document, legacy_motion=legacy,
        )
        source = first.document["source"]
        self.assertEqual(set(source) - {"kind"}, {
            "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
            "raw_npz_sha256", "source_sha256", "map_sha256",
            "array_inventory_sha256",
        })

    def test_build_does_not_decode_or_recompile_raw_npz(self):
        bundle, camera, projected, legacy = artifacts()
        with patch(
            "autospine_workbench.kimodo_npz_reader.decode_kimodo_npz",
            side_effect=AssertionError("raw decode must not run"),
        ), patch(
            "autospine_workbench.kimodo_npz_compiler.compile_kimodo_npz_motion",
            side_effect=AssertionError("raw compile must not run"),
        ):
            build_projected_motion_compile_run(
                bundle, camera, projected, legacy
            )

    def test_exact_fields_and_compiler_identity_fail_closed(self):
        bundle, camera, projected, legacy = artifacts()
        baseline = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        ).document
        mutations = []
        for path in (("extra",), ("source", "extra"), ("camera", "extra"),
                     ("compiler", "extra"), ("validation", "extra"),
                     ("output", "extra")):
            candidate = deepcopy(baseline)
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = True
            mutations.append(candidate)
        for field, value in (("id", "other"), ("version", "1.0.1")):
            candidate = deepcopy(baseline)
            candidate["compiler"][field] = value
            mutations.append(candidate)
        candidate = deepcopy(baseline)
        candidate["compiler"]["config"]["depth_use"] = "ordering"
        mutations.append(candidate)
        for candidate in mutations:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ProjectedMotionCompileRunError):
                    require_projected_motion_compile_run(candidate)

    def test_sha_finite_and_metric_bounds_fail_closed(self):
        bundle, camera, projected, legacy = artifacts()
        baseline = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        ).document
        candidates = []
        for container, field in (
            ("source", "motion_ir_sha256"),
            ("camera", "camera_sha256"),
            ("output", "projected_motion_ir_sha256"),
        ):
            candidate = deepcopy(baseline)
            candidate[container][field] = "A" * 64
            candidates.append(candidate)
        for field, value in (
            ("max_global_matrix_error", math.nan),
            ("max_heading_norm_error", math.inf),
            ("max_position_error_meters", 0.0005001),
            ("collapsed_sample_count", -1),
            ("minimum_foreshortening_ratio", -0.1),
            ("maximum_foreshortening_ratio", 1.002),
        ):
            candidate = deepcopy(baseline)
            candidate["validation"][field] = value
            candidates.append(candidate)
        candidate = deepcopy(baseline)
        candidate["validation"]["minimum_foreshortening_ratio"] = 0.8
        candidate["validation"]["maximum_foreshortening_ratio"] = 0.7
        candidates.append(candidate)
        candidate = deepcopy(baseline)
        candidate["output"]["legacy_motion_ir_sha256"] = "f" * 64
        candidates.append(candidate)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ProjectedMotionCompileRunError):
                    require_projected_motion_compile_run(candidate)

    def test_optional_cross_bindings_detect_artifact_drift(self):
        bundle, camera, projected, legacy = artifacts()
        run = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        ).document
        changed_camera = deepcopy(camera)
        changed_camera["depth_positive"] = "toward_camera"
        with self.assertRaisesRegex(ProjectedMotionCompileRunError, "camera"):
            require_projected_motion_compile_run(run, camera=changed_camera)
        changed_projected = projected.document
        changed_projected["source"]["map_sha256"] = "a" * 64
        with self.assertRaisesRegex(ProjectedMotionCompileRunError,
                                    "ProjectedMotionIR"):
            require_projected_motion_compile_run(
                run, projected_motion=changed_projected
            )
        changed_legacy = deepcopy(legacy)
        changed_legacy["clip_id"] = "changed"
        with self.assertRaisesRegex(ProjectedMotionCompileRunError, "Legacy"):
            require_projected_motion_compile_run(
                run, legacy_motion=changed_legacy
            )

    def test_projected_metrics_are_recomputed_when_output_is_supplied(self):
        bundle, camera, projected, legacy = artifacts()
        run = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        ).document
        run["validation"]["collapsed_sample_count"] += 1
        with self.assertRaisesRegex(ProjectedMotionCompileRunError, "metrics"):
            require_projected_motion_compile_run(
                run, projected_motion=projected.document
            )

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("jsonschema"),
        "jsonschema is optional",
    )
    def test_schema_and_semantic_validator_have_parity(self):
        import jsonschema

        bundle, camera, projected, legacy = artifacts()
        value = build_projected_motion_compile_run(
            bundle, camera, projected, legacy
        ).document
        schema = json.loads((
            ROOT / "schemas" / "projected-motion-compile-run-v1.schema.json"
        ).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        bad_values = []
        extra = deepcopy(value)
        extra["camera"]["extra"] = True
        bad_values.append(extra)
        bad_sha = deepcopy(value)
        bad_sha["source"]["map_sha256"] = "A" * 64
        bad_values.append(bad_sha)
        bad_bound = deepcopy(value)
        bad_bound["validation"]["maximum_foreshortening_ratio"] = 1.01
        bad_values.append(bad_bound)
        for candidate in bad_values:
            with self.assertRaises(ProjectedMotionCompileRunError):
                require_projected_motion_compile_run(candidate)
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(candidate)


if __name__ == "__main__":
    unittest.main()
