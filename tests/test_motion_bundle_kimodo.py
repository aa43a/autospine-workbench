"""Immutable bundle publication and secure replay tests for Kimodo NPZ."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_compile_run import (
    build_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import compile_kimodo_npz_motion
from autospine_workbench.motion_bundle_contract import (
    KIMODO_DOCUMENT_NAMES,
    MotionBundleContractError,
    build_motion_bundle_contract,
    motion_bundle_address_sha256,
)
from autospine_workbench.motion_bundle_integrity import (
    MotionBundleIntegrityError,
    MotionBundleSnapshot,
    verify_motion_bundle_snapshot,
)
from autospine_workbench.motion_bundle_reader import (
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from autospine_workbench.motion_bundle_store import (
    MotionBundleStore,
    MotionBundleStoreError,
)
from tests.fixtures.kimodo_npz_archive import (
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document


class KimodoBundleFixture:
    def __init__(self, root: Path, *, compression=zipfile.ZIP_STORED):
        self.state = root / "state"
        self.raw = build_npz(
            motion_member_bytes(), compression=compression
        )
        self.source = source_document(self.raw)
        self.mapping = map_document()
        self.compiled = compile_kimodo_npz_motion(
            self.raw, self.source, self.mapping
        )
        self.run = build_kimodo_npz_compile_run(
            self.raw, self.source, self.mapping, self.compiled.document
        )
        self.contract = build_motion_bundle_contract(
            self.compiled.document, self.run.document,
            raw_npz=self.raw, kimodo_source=self.source,
            kimodo_map=self.mapping,
        )

    def publish(self):
        return MotionBundleStore(self.state).publish(
            self.compiled.document, self.run.document,
            raw_npz=self.raw, kimodo_source=self.source,
            kimodo_map=self.mapping,
        )


class MotionBundleKimodoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_contract_binds_five_exact_documents_and_isolated_accessors(self):
        fixture = KimodoBundleFixture(self.root)
        contract = fixture.contract
        self.assertEqual("kimodo_npz", contract.source_kind)
        self.assertEqual(KIMODO_DOCUMENT_NAMES, contract.inventory)
        self.assertEqual(fixture.raw, contract.raw_npz)
        self.assertEqual(fixture.source, contract.kimodo_source)
        self.assertEqual(fixture.mapping, contract.kimodo_map)
        self.assertIsNone(contract.raw_bvh)
        self.assertIsNone(contract.bvh_map)
        self.assertEqual(
            contract.bundle_sha256,
            motion_bundle_address_sha256(tuple(contract.document_bytes.items())),
        )
        changed = contract.kimodo_source
        changed["source_id"] = "changed"
        self.assertNotEqual(changed, contract.kimodo_source)

    def test_publish_secure_read_reuse_and_properties_round_trip(self):
        fixture = KimodoBundleFixture(self.root)
        first, second = fixture.publish(), fixture.publish()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        verified = VerifiedMotionBundleReader(fixture.state).load(
            first.clip_sha256, first.bundle_sha256
        )
        self.assertEqual("kimodo_npz", verified.source_kind)
        self.assertEqual(KIMODO_DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(fixture.raw, verified.raw_npz)
        self.assertEqual(fixture.source, verified.kimodo_source)
        self.assertEqual(fixture.mapping, verified.kimodo_map)
        self.assertIsNone(verified.raw_bvh)
        self.assertIsNone(verified.bvh_map)

    def test_archive_or_sidecar_drift_keeps_clip_but_changes_run_and_bundle(self):
        stored = KimodoBundleFixture(self.root / "stored", compression=zipfile.ZIP_STORED)
        deflated = KimodoBundleFixture(
            self.root / "deflated", compression=zipfile.ZIP_DEFLATED
        )
        self.assertEqual(stored.compiled.sha256, deflated.compiled.sha256)
        self.assertEqual(stored.contract.clip_sha256, deflated.contract.clip_sha256)
        self.assertNotEqual(stored.run.sha256, deflated.run.sha256)
        self.assertNotEqual(stored.contract.bundle_sha256,
                            deflated.contract.bundle_sha256)

        changed_source = deepcopy(stored.source)
        changed_source["producer"]["reason_code"] = "legacy_export"
        changed_run = build_kimodo_npz_compile_run(
            stored.raw, changed_source, stored.mapping, stored.compiled.document
        )
        changed = build_motion_bundle_contract(
            stored.compiled.document, changed_run.document,
            raw_npz=stored.raw, kimodo_source=changed_source,
            kimodo_map=stored.mapping,
        )
        self.assertEqual(stored.contract.clip_sha256, changed.clip_sha256)
        self.assertNotEqual(stored.contract.bundle_sha256, changed.bundle_sha256)

    def test_each_tampered_missing_extra_or_case_file_fails_secure_replay(self):
        for name in KIMODO_DOCUMENT_NAMES:
            fixture = KimodoBundleFixture(self.root / name.replace(".", "-"))
            published = fixture.publish()
            path = published.path / name
            path.write_bytes(path.read_bytes() + b"\x00")
            with self.subTest(name=name), self.assertRaises(
                VerifiedMotionBundleReaderError
            ):
                VerifiedMotionBundleReader(fixture.state).load(
                    published.clip_sha256, published.bundle_sha256
                )

        for mutation in ("missing", "extra", "case"):
            fixture = KimodoBundleFixture(self.root / mutation)
            published = fixture.publish()
            if mutation == "missing":
                (published.path / "sidecar.json").unlink()
            elif mutation == "extra":
                (published.path / "extra.json").write_text("{}")
            else:
                source = published.path / "sidecar.json"
                source.rename(published.path / "SIDECAR.JSON")
            with self.subTest(mutation=mutation), self.assertRaises(
                VerifiedMotionBundleReaderError
            ):
                VerifiedMotionBundleReader(fixture.state).load(
                    published.clip_sha256, published.bundle_sha256
                )

    def test_direct_snapshot_order_mixed_sources_and_limits_fail_closed(self):
        fixture = KimodoBundleFixture(self.root)
        items = tuple(fixture.contract.document_bytes.items())
        path = self.root / "motions" / fixture.contract.clip_sha256 \
            / fixture.contract.bundle_sha256
        reversed_snapshot = MotionBundleSnapshot(path, tuple(reversed(items)))
        with self.assertRaises(MotionBundleIntegrityError):
            verify_motion_bundle_snapshot(
                reversed_snapshot,
                expected_clip_sha256=fixture.contract.clip_sha256,
                expected_bundle_sha256=fixture.contract.bundle_sha256,
            )
        with self.assertRaisesRegex(MotionBundleContractError, "mixed"):
            build_motion_bundle_contract(
                fixture.compiled.document, fixture.run.document,
                raw_bvh=b"BVH", bvh_map={}, raw_npz=fixture.raw,
                kimodo_source=fixture.source, kimodo_map=fixture.mapping,
            )
        for field in (
            "MAX_RAW_NPZ_BYTES", "MAX_KIMODO_SOURCE_BYTES",
            "MAX_KIMODO_MAP_BYTES", "MAX_KIMODO_RUN_BYTES",
            "MAX_KIMODO_TOTAL_DOCUMENT_BYTES",
        ):
            with self.subTest(field=field), patch(
                f"autospine_workbench.motion_bundle_contract.{field}", 1
            ), self.assertRaisesRegex(MotionBundleContractError, "resource limit"):
                build_motion_bundle_contract(
                    fixture.compiled.document, fixture.run.document,
                    raw_npz=fixture.raw, kimodo_source=fixture.source,
                    kimodo_map=fixture.mapping,
                )

    def test_incomplete_kimodo_input_creates_no_store_state(self):
        fixture = KimodoBundleFixture(self.root)
        with self.assertRaisesRegex(MotionBundleStoreError, "input is invalid"):
            MotionBundleStore(fixture.state).publish(
                fixture.compiled.document, fixture.run.document,
                raw_npz=fixture.raw,
            )
        self.assertFalse(fixture.state.exists())


if __name__ == "__main__":
    unittest.main()
