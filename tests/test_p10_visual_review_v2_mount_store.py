"""Persistent non-authoritative P10.3c v2 mount cache tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_preview_v2_service import (  # noqa: E402
    _compile_record, _locator, p10_preview_v2_record_is_current,
)
from autospine_workbench.p10_visual_review_v2_mount_snapshot import (  # noqa: E402
    canonical_mount_snapshot,
)
from autospine_workbench.p10_visual_review_v2_mount_store import (  # noqa: E402
    MAX_MOUNT_SNAPSHOT_BYTES, NAMESPACE,
    P10VisualReviewV2MountStore,
    P10VisualReviewV2MountStoreError,
)
from tests.test_p10_preview_v2_commands import _PackageFixture  # noqa: E402


def _sha(character: str) -> str:
    return character * 64


class P10VisualReviewV2MountStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = _PackageFixture(Path(cls.temporary.name))
        with cls.fixture.current_chains():
            locator = _locator(cls.fixture.store, cls.fixture.package_id)
            cls.record = _compile_record(cls.fixture.store, locator)
        cls.store = P10VisualReviewV2MountStore(cls.fixture.state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_missing_snapshot_is_a_cache_miss(self):
        self.assertIsNone(self.store.load(
            _sha("0"), self.record.key.locator,
            expected_preview_sha256=
                self.record.result.temporary_preview_v2_sha256,
            expected_artifact_set_sha256=
                self.record.result.artifact_set_sha256,
        ))

    def test_round_trip_rebuilds_every_exact_value(self):
        job = _sha("1")
        self.store.save(job, self.record)
        loaded = self._load(job)
        self.assertEqual(self.record.key, loaded.key)
        self.assertEqual(self.record.address, loaded.address)
        self.assertEqual(
            self.record.candidates.canonical_bytes,
            loaded.candidates.canonical_bytes,
        )
        self.assertEqual(
            self.record.framing_candidate.canonical_bytes,
            loaded.framing_candidate.canonical_bytes,
        )
        self.assertEqual(
            self.record.result._preview.canonical_bytes,
            loaded.result._preview.canonical_bytes,
        )
        self.assertEqual(
            self.record.result.artifact_bytes,
            loaded.result.artifact_bytes,
        )

    def test_snapshot_does_not_persist_locator_paths_or_runtime_identity(self):
        job = _sha("2")
        self.store.save(job, self.record)
        text = self._path(job).read_text(encoding="utf-8")
        self.assertNotIn(str(self.fixture.state), text)
        self.assertNotIn(str(self.fixture.store.workspace_root), text)
        self.assertIn(
            f'"preview_compiler_sha256":'
            f'"{self.record.key.locator.compiler_inventory_sha256}"',
            text,
        )
        self.assertNotIn("state_root", text)
        self.assertNotIn("workspace_root", text)
        self.assertIn(f'"package_id":"{self.fixture.package_id}"', text)

    def test_different_preview_compiler_cannot_hit_snapshot(self):
        job = _sha("f")
        self.store.save(job, self.record)
        locator = replace(
            self.record.key.locator,
            compiler_inventory_sha256=_sha("e"),
        )
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.load(
                job, locator,
                expected_preview_sha256=
                    self.record.result.temporary_preview_v2_sha256,
                expected_artifact_set_sha256=
                    self.record.result.artifact_set_sha256,
            )

    def test_current_validator_rejects_inventory_only_tamper(self):
        changed = replace(
            self.record,
            key=replace(self.record.key, inventory_sha256=_sha("e")),
        )
        with self.fixture.current_chains():
            self.assertFalse(p10_preview_v2_record_is_current(
                self.fixture.store, changed,
            ))

    def test_tampered_compiler_and_old_v2_snapshot_are_rejected(self):
        tampered, old = _sha("0"), _sha("9")
        self.store.save(tampered, self.record)
        document = self._document(tampered)
        document["preview_compiler_sha256"] = _sha("e")
        self._path(tampered).write_bytes(canonical_mount_snapshot(document))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(tampered)

        self.store.save(old, self.record)
        document = self._document(old)
        document["format_version"] = 2
        self._path(old).write_bytes(canonical_mount_snapshot(document))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(old)

    def test_wrong_expected_preview_or_artifact_fails_closed(self):
        job = _sha("3")
        self.store.save(job, self.record)
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.load(
                job, self.record.key.locator,
                expected_preview_sha256=_sha("e"),
                expected_artifact_set_sha256=
                    self.record.result.artifact_set_sha256,
            )
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.load(
                job, self.record.key.locator,
                expected_preview_sha256=
                    self.record.result.temporary_preview_v2_sha256,
                expected_artifact_set_sha256=_sha("e"),
            )

    def test_wrong_package_locator_fails_closed(self):
        job = _sha("4")
        self.store.save(job, self.record)
        locator = replace(self.record.key.locator, package_id=_sha("e"))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.load(
                job, locator,
                expected_preview_sha256=
                    self.record.result.temporary_preview_v2_sha256,
                expected_artifact_set_sha256=
                    self.record.result.artifact_set_sha256,
            )

    def test_noncanonical_json_and_invalid_base64_are_rejected(self):
        noncanonical, invalid = _sha("5"), _sha("6")
        self.store.save(noncanonical, self.record)
        document = self._document(noncanonical)
        self._path(noncanonical).write_text(
            json.dumps(document, indent=2), encoding="utf-8",
        )
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(noncanonical)

        self.store.save(invalid, self.record)
        document = self._document(invalid)
        document["preview"]["artifacts"][0]["base64"] = "%%%"
        self._path(invalid).write_bytes(canonical_mount_snapshot(document))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(invalid)

    def test_tampered_candidate_and_preview_seals_are_rejected(self):
        candidate, preview = _sha("7"), _sha("8")
        self.store.save(candidate, self.record)
        document = self._document(candidate)
        document["cache_key"]["p10_candidate_sha256"] = _sha("e")
        self._path(candidate).write_bytes(canonical_mount_snapshot(document))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(candidate)

        self.store.save(preview, self.record)
        document = self._document(preview)
        document["preview"]["manifest_sha256"] = _sha("e")
        self._path(preview).write_bytes(canonical_mount_snapshot(document))
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(preview)

    def test_case_alias_and_oversized_snapshot_are_errors(self):
        alias = _sha("a")
        parent = self._path(alias).parent
        parent.mkdir(parents=True, exist_ok=True)
        (parent / f"{alias.upper()}.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(alias)

        oversized = _sha("b")
        self.store.save(oversized, self.record)
        with patch(
            "autospine_workbench.p10_visual_review_v2_mount_store."
            "MAX_MOUNT_SNAPSHOT_BYTES",
            len(self._path(oversized).read_bytes()) - 1,
        ), self.assertRaises(P10VisualReviewV2MountStoreError):
            self._load(oversized)

    def test_failed_replace_preserves_previous_snapshot(self):
        job = _sha("c")
        self.store.save(job, self.record)
        before = self._path(job).read_bytes()
        with patch(
            "autospine_workbench.p10_visual_review_v2_mount_store.os.replace",
            side_effect=OSError("injected"),
        ), self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.save(job, self.record)
        self.assertEqual(before, self._path(job).read_bytes())

    def test_save_rejects_cross_wired_result(self):
        changed = replace(
            self.record.result, temporary_preview_v2_sha256=_sha("e"),
        )
        with self.assertRaises(P10VisualReviewV2MountStoreError):
            self.store.save(
                _sha("d"), replace(self.record, result=changed),
            )

    def _load(self, job):
        return self.store.load(
            job, self.record.key.locator,
            expected_preview_sha256=
                self.record.result.temporary_preview_v2_sha256,
            expected_artifact_set_sha256=
                self.record.result.artifact_set_sha256,
        )

    def _path(self, job):
        return self.fixture.state / "cache" / NAMESPACE / f"{job}.json"

    def _document(self, job):
        return deepcopy(json.loads(self._path(job).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
