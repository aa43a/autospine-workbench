"""P9.0 exact ancillary evidence contract and compiler tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_camera_projection import (  # noqa: E402
    compile_verified_kimodo_projection,
)
from autospine_workbench.kimodo_npz_compile_run import (  # noqa: E402
    build_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import (  # noqa: E402
    compile_kimodo_npz_motion,
)
from autospine_workbench.kimodo_npz_consistency import (  # noqa: E402
    KimodoNpzConsistencyError,
)
from autospine_workbench.kimodo_npz_reader import (  # noqa: E402
    KimodoNpzReaderError,
)
from autospine_workbench.kimodo_policy_evidence import (  # noqa: E402
    KimodoPolicyEvidenceError,
    compile_kimodo_policy_evidence,
)
from autospine_workbench.kimodo_policy_evidence_arrays import (  # noqa: E402
    extract_kimodo_policy_arrays,
)
from autospine_workbench.kimodo_policy_evidence_validation import (  # noqa: E402
    KimodoPolicyEvidenceValidationError,
    require_kimodo_policy_evidence,
)
from autospine_workbench.motion_bundle_integrity import (  # noqa: E402
    VerifiedMotionBundle,
)
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReader,
)
from autospine_workbench.projected_motion_bundle_store import (  # noqa: E402
    ProjectedMotionBundleStore,
)
from autospine_workbench.projected_motion_compile_run import (  # noqa: E402
    build_projected_motion_compile_run,
)
from autospine_workbench.projected_motion_legacy import (  # noqa: E402
    compile_projected_motion_to_motion_ir,
)
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npy,
    build_npz,
    float_payload,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402
from tests.test_kimodo_camera_projection import camera_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


def _bundles(root: Path, *, inventory: str = "complete-v1", loop: bool = False):
    state = Path(root) / "state"
    raw = build_npz(motion_member_bytes(inventory=inventory, loop=loop))
    source = source_document(raw, inventory=inventory)
    mapping = map_document()
    compiled = compile_kimodo_npz_motion(raw, source, mapping)
    run = build_kimodo_npz_compile_run(raw, source, mapping, compiled.document)
    published = MotionBundleStore(state).publish(
        compiled.document, run.document,
        raw_npz=raw, kimodo_source=source, kimodo_map=mapping,
    )
    p7 = VerifiedMotionBundleReader(state).load(
        published.clip_sha256, published.bundle_sha256
    )
    camera = camera_document(mapping)
    projected = compile_verified_kimodo_projection(p7, camera)
    legacy = compile_projected_motion_to_motion_ir(projected.document)
    p8_run = build_projected_motion_compile_run(p7, camera, projected, legacy)
    p8_published = ProjectedMotionBundleStore(state).publish(
        camera, projected.document, p8_run.document
    )
    p8 = VerifiedProjectedMotionBundleReader(state).load(
        p8_published.projected_motion_sha256, p8_published.bundle_sha256
    )
    return p7, p8


def _forged_raw_bundle(p7: VerifiedMotionBundle, raw: bytes) -> VerifiedMotionBundle:
    documents = p7.document_bytes
    source = source_document(raw)
    documents["source.npz"] = raw
    documents["sidecar.json"] = json.dumps(
        source, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return VerifiedMotionBundle(
        path=p7.path,
        clip_id=p7.clip_id,
        clip_sha256=p7.clip_sha256,
        run_sha256=p7.run_sha256,
        bundle_sha256=p7.bundle_sha256,
        source_kind=p7.source_kind,
        _document_items=tuple((name, documents[name]) for name in p7.inventory),
    )


class KimodoPolicyEvidenceTests(unittest.TestCase):
    def test_complete_profile_is_deterministic_and_preserves_raw_channels(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            first = compile_kimodo_policy_evidence(p7, p8)
            second = compile_kimodo_policy_evidence(p7, p8)
            self.assertEqual(first.canonical_bytes, second.canonical_bytes)
            self.assertEqual(first.sha256, second.sha256)
            document = first.document
            require_kimodo_policy_evidence(
                document, p7_bundle=p7, p8_bundle=p8
            )
            self._schema(document)

            self.assertEqual("evidence_only", document["policy"]["mode"])
            self.assertFalse(document["policy"]["candidate_emitted"])
            contacts = document["signals"]["foot_contact_channels"]
            self.assertEqual(4, len(contacts["channels"]))
            self.assertEqual(
                [True, False, False], contacts["channels"][0]["values"]
            )
            self.assertEqual(
                [False, True, False], contacts["channels"][2]["values"]
            )
            heading = document["signals"]["global_root_heading"]
            self.assertEqual("available", heading["status"])
            self.assertEqual(
                "source_two_component_uninterpreted",
                heading["coordinate_space"],
            )
            self.assertEqual([[0.0, 1.0]] * 3, heading["values"])
            smooth = document["signals"]["smooth_root_position"]
            self.assertEqual("available", smooth["status"])
            self.assertAlmostEqual(0.1, smooth["values"][1][0], places=6)

            changed = first.document
            changed["signals"]["global_root_heading"]["values"][0][0] = 1.0
            self.assertNotEqual(changed, first.document)

    def test_core_profile_marks_only_missing_arrays_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary), inventory="core-v1")
            document = compile_kimodo_policy_evidence(p7, p8).document
            require_kimodo_policy_evidence(
                document, p7_bundle=p7, p8_bundle=p8
            )
            self._schema(document)
            signals = document["signals"]
            self.assertEqual("available", signals["foot_contact_channels"]["status"])
            expected = {
                "status": "unavailable",
                "reason_code": "array_not_in_core_v1",
            }
            for name, source_array in (
                ("global_root_heading", "global_root_heading"),
                ("smooth_root_position", "smooth_root_pos"),
            ):
                self.assertEqual(
                    {**expected, "source_array": source_array}, signals[name]
                )

    def test_every_source_digest_and_p7_p8_pair_are_cross_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            p7, p8 = _bundles(root / "first")
            other_p7, other_p8 = _bundles(root / "other", loop=True)
            with self.assertRaisesRegex(KimodoPolicyEvidenceError, "cross-bound"):
                compile_kimodo_policy_evidence(p7, other_p8)
            with self.assertRaises(KimodoPolicyEvidenceError):
                compile_kimodo_policy_evidence(other_p7, p8)

            baseline = compile_kimodo_policy_evidence(p7, p8).document
            for field in baseline["source"]:
                changed = deepcopy(baseline)
                changed["source"][field] = "0" * 64
                with self.subTest(field=field), self.assertRaises(
                    KimodoPolicyEvidenceValidationError
                ):
                    require_kimodo_policy_evidence(
                        changed, p7_bundle=p7, p8_bundle=p8
                    )
            changed = deepcopy(baseline)
            changed["signals"]["foot_contact_channels"]["channels"][0][
                "values"
            ][0] = False
            with self.assertRaisesRegex(
                KimodoPolicyEvidenceValidationError, "ancillary arrays"
            ):
                require_kimodo_policy_evidence(
                    changed, p7_bundle=p7, p8_bundle=p8
                )

    def test_complete_bad_shape_nonfinite_and_nonunit_heading_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            cases = []
            shape = motion_member_bytes()
            shape["global_root_heading.npy"] = build_npy(
                "<f4", (3, 3), float_payload((3, 3), [0.0] * 9)
            )
            cases.append((shape, KimodoNpzReaderError))
            nonfinite = motion_member_bytes()
            values = [0.0] * 9
            values[0] = math.nan
            nonfinite["smooth_root_pos.npy"] = build_npy(
                "<f4", (3, 3), float_payload((3, 3), values)
            )
            cases.append((nonfinite, KimodoNpzReaderError))
            nonunit = motion_member_bytes()
            nonunit["global_root_heading.npy"] = build_npy(
                "<f4", (3, 2), float_payload((3, 2), [0.0] * 6)
            )
            cases.append((nonunit, KimodoNpzConsistencyError))

            for members, direct_error in cases:
                raw = build_npz(members)
                source = source_document(raw)
                with self.subTest(error=direct_error.__name__), self.assertRaises(
                    direct_error
                ):
                    extract_kimodo_policy_arrays(raw, source)
                forged = _forged_raw_bundle(p7, raw)
                with self.assertRaises(KimodoPolicyEvidenceError):
                    compile_kimodo_policy_evidence(forged, p8)

    def test_standalone_validator_rejects_policy_and_unit_vector_guessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            baseline = compile_kimodo_policy_evidence(p7, p8).document
            changed = deepcopy(baseline)
            changed["policy"]["candidate_emitted"] = True
            with self.assertRaisesRegex(
                KimodoPolicyEvidenceValidationError, "evidence-only"
            ):
                require_kimodo_policy_evidence(changed)
            changed = deepcopy(baseline)
            changed["signals"]["global_root_heading"]["values"][0] = [0.0, 0.0]
            with self.assertRaisesRegex(
                KimodoPolicyEvidenceValidationError, "unit direction"
            ):
                require_kimodo_policy_evidence(changed)

    def _schema(self, document: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "kimodo-policy-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
