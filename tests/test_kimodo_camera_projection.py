"""Camera geometry and reproducibility tests for P8 ProjectedMotionIR."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_camera_projection import (  # noqa: E402
    KimodoCameraProjectionError,
    compile_verified_kimodo_projection,
    projected_motion_compiler_config,
)
from autospine_workbench.kimodo_npz_compile_run import (  # noqa: E402
    build_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import (  # noqa: E402
    compile_kimodo_npz_motion,
)
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    build_motion_bundle_contract,
)
from autospine_workbench.motion_bundle_integrity import (  # noqa: E402
    VerifiedMotionBundle,
)
from autospine_workbench.projected_motion_validation import (  # noqa: E402
    require_projected_motion_ir,
)
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402


def camera_document(mapping: dict, *, depth_positive="away_from_camera") -> dict:
    return {
        "format": "autospine-camera-model",
        "format_version": 1,
        "camera_id": "kimodo-test-camera-v1",
        "projection": "static_orthographic",
        "basis": {
            field: mapping["basis"][field]
            for field in ("screen_x", "screen_y", "depth")
        },
        "depth_positive": depth_positive,
        "origin": "source_root_frame0",
        "normalization": "map_reference_length",
        "reference_length_meters":
            mapping["root"]["reference_length_meters"],
    }


def verified_fixture(*, offsets=None, basis=None):
    raw = build_npz(motion_member_bytes(offset_overrides=offsets))
    source = source_document(raw)
    mapping = map_document()
    if basis is not None:
        mapping["basis"].update(basis)
    compiled = compile_kimodo_npz_motion(raw, source, mapping)
    run = build_kimodo_npz_compile_run(
        raw, source, mapping, compiled.document
    )
    contract = build_motion_bundle_contract(
        compiled.document,
        run.document,
        raw_npz=raw,
        kimodo_source=source,
        kimodo_map=mapping,
    )
    bundle = VerifiedMotionBundle(
        path=ROOT / "state" / "motions" / contract.clip_sha256
            / contract.bundle_sha256,
        clip_id=contract.clip_id,
        clip_sha256=contract.clip_sha256,
        run_sha256=contract.run_sha256,
        bundle_sha256=contract.bundle_sha256,
        source_kind=contract.source_kind,
        _document_items=tuple(contract.document_bytes.items()),
    )
    return bundle, mapping


def track(document: dict, role: str) -> dict:
    return next(row for row in document["segment_tracks"] if row["role"] == role)


class KimodoCameraProjectionTests(unittest.TestCase):
    def test_in_plane_motion_is_deterministic_and_fully_bound(self):
        bundle, mapping = verified_fixture()
        camera = camera_document(mapping)
        first = compile_verified_kimodo_projection(bundle, camera)
        second = compile_verified_kimodo_projection(bundle, deepcopy(camera))
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        require_projected_motion_ir(first.document)
        self.assertEqual(bundle.clip_sha256,
                         first.document["source"]["motion_ir_sha256"])
        self.assertEqual(bundle.bundle_sha256,
                         first.document["source"]["motion_bundle_sha256"])
        self.assertEqual(bundle.run_sha256,
                         first.document["source"]["motion_run_sha256"])
        self.assertTrue(all(
            sample["foreshortening_ratio"] == 1.0
            for row in first.document["segment_tracks"]
            for sample in row["samples"]
        ))
        self.assertEqual(0, dict(first.projection_metrics)[
            "collapsed_sample_count"
        ])

    def test_sixty_degree_depth_tilt_has_half_projected_length(self):
        bundle, mapping = verified_fixture(offsets={
            "LeftForeArm": (0.1, 0.0, math.sqrt(3.0) * 0.1),
        })
        result = compile_verified_kimodo_projection(
            bundle, camera_document(mapping)
        ).document
        samples = track(result, "humanoid.arm.upper.left")["samples"]
        self.assertTrue(all(
            math.isclose(row["foreshortening_ratio"], 0.5, abs_tol=1e-7)
            for row in samples
        ))
        self.assertTrue(all(
            math.isclose(
                row["depth_cosine"], math.sqrt(3.0) / 2.0, abs_tol=1e-7
            )
            for row in samples
        ))
        self.assertTrue(all(math.isclose(
            row["foreshortening_ratio"] ** 2 + row["depth_cosine"] ** 2,
            1.0,
            abs_tol=1e-7,
        ) for row in samples))

    def test_depth_axis_sign_changes_evidence_not_projected_length(self):
        offsets = {"LeftForeArm": (0.1, 0.0, 0.1)}
        positive, map_positive = verified_fixture(offsets=offsets)
        negative, map_negative = verified_fixture(
            offsets=offsets, basis={"depth": "-Z"}
        )
        left = track(compile_verified_kimodo_projection(
            positive, camera_document(map_positive)
        ).document, "humanoid.arm.upper.left")["samples"][0]
        right = track(compile_verified_kimodo_projection(
            negative, camera_document(map_negative)
        ).document, "humanoid.arm.upper.left")["samples"][0]
        self.assertEqual(left["projected_length_normalized"],
                         right["projected_length_normalized"])
        self.assertEqual(left["foreshortening_ratio"],
                         right["foreshortening_ratio"])
        self.assertEqual(left["depth_cosine"], -right["depth_cosine"])

    def test_camera_semantics_are_content_addressed_and_cross_checked(self):
        bundle, mapping = verified_fixture()
        camera = camera_document(mapping)
        away = compile_verified_kimodo_projection(bundle, camera)
        camera["depth_positive"] = "toward_camera"
        toward = compile_verified_kimodo_projection(bundle, camera)
        self.assertNotEqual(away.sha256, toward.sha256)
        self.assertEqual(
            away.document["segment_tracks"],
            toward.document["segment_tracks"],
        )

        camera["basis"]["screen_x"] = "+Y"
        camera["basis"]["screen_y"] = "-X"
        with self.assertRaisesRegex(KimodoCameraProjectionError, "basis differs"):
            compile_verified_kimodo_projection(bundle, camera)

    def test_non_kimodo_input_and_compiler_config_fail_noiselessly(self):
        bundle, mapping = verified_fixture()
        wrong = VerifiedMotionBundle(
            path=bundle.path,
            clip_id=bundle.clip_id,
            clip_sha256=bundle.clip_sha256,
            run_sha256=bundle.run_sha256,
            bundle_sha256=bundle.bundle_sha256,
            source_kind="builtin",
            _document_items=bundle._document_items,
        )
        with self.assertRaisesRegex(KimodoCameraProjectionError, "verified Kimodo"):
            compile_verified_kimodo_projection(wrong, camera_document(mapping))
        self.assertEqual("evidence-only-no-ordering-v1",
                         projected_motion_compiler_config()["depth_use"])


if __name__ == "__main__":
    unittest.main()
