"""Immutable store and exact historical reader tests for P10.5d v2."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_bundle_contract_v2 import (  # noqa: E402
    DOCUMENT_NAMES,
    BodySwayDynamicSeamBundleContractV2Error,
    build_body_sway_dynamic_seam_bundle_contract_v2,
)
from autospine_workbench.body_sway_dynamic_seam_bundle_reader_v2 import (  # noqa: E402
    BodySwayDynamicSeamBundleReaderV2,
    BodySwayDynamicSeamBundleReaderV2Error,
)
from autospine_workbench.body_sway_dynamic_seam_bundle_store_v2 import (  # noqa: E402
    BodySwayDynamicSeamBundleStoreV2,
    BodySwayDynamicSeamBundleStoreV2Error,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)


CONTRACT = (
    "autospine_workbench.body_sway_dynamic_seam_bundle_contract_v2."
)


def _documents():
    source = {
        "format": "autospine-body-sway-dynamic-seam-source",
        "format_version": 2,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "source_set_sha256": "a" * 64,
    }
    probe = {
        "format": "autospine-body-sway-dynamic-seam-probe",
        "format_version": 2,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "source": deepcopy(source),
        "status": "indeterminate",
        "summary": {"segment_count": 1},
        "claims": {"release_authority": False},
        "release_gate": {"status": "blocked"},
    }
    return source, probe


@contextmanager
def _validated_documents():
    def admit(source):
        expected, _probe = _documents()
        if source != expected:
            raise ValueError("source tamper")
        return deepcopy(source)

    def probe_sha(probe):
        _source, expected = _documents()
        if probe != expected:
            raise ValueError("probe tamper")
        return canonical_sha256(probe)

    with patch(
        CONTRACT + "require_body_sway_dynamic_seam_source_v2",
        side_effect=admit,
    ), patch(
        CONTRACT + "body_sway_dynamic_seam_probe_sha256_v2",
        side_effect=probe_sha,
    ):
        yield


class BodySwayDynamicSeamBundleV2Tests(unittest.TestCase):
    def test_atomic_publish_exact_readback_and_deterministic_reuse(self):
        source, probe = _documents()
        with tempfile.TemporaryDirectory() as temporary, \
                _validated_documents():
            root = Path(temporary)
            store = BodySwayDynamicSeamBundleStoreV2(root)
            first = store.publish(source, probe)
            second = store.publish(source, probe)
            verified = BodySwayDynamicSeamBundleReaderV2(root).load(
                "fixture-project", first.probe_sha256,
                first.bundle_sha256,
            )
            children = list(first.path.parent.iterdir())
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
        self.assertEqual(source, verified.source)
        self.assertEqual(probe, verified.probe)
        self.assertEqual(set(DOCUMENT_NAMES), set(verified.document_bytes))
        self.assertEqual(
            "historical_exact_bytes_only",
            verified.manifest["authority_scope"],
        )
        self.assertFalse(any(verified.manifest["claims"].values()))
        self.assertFalse(any(path.name.startswith(".") for path in children))

    def test_contract_manifest_binds_names_sizes_digests_and_source(self):
        source, probe = _documents()
        with _validated_documents():
            contract = build_body_sway_dynamic_seam_bundle_contract_v2(
                source, probe,
            )
        manifest = contract.manifest
        self.assertEqual(list(DOCUMENT_NAMES[:2]), [
            row["name"] for row in manifest["documents"]
        ])
        for row in manifest["documents"]:
            data = contract.document_bytes[row["name"]]
            self.assertEqual(len(data), row["size_bytes"])
            self.assertEqual(canonical_sha256(json.loads(data)), row[
                "sha256"
            ])
        attack = deepcopy(probe)
        attack["source"]["source_set_sha256"] = "b" * 64
        with _validated_documents(), self.assertRaises(
            BodySwayDynamicSeamBundleContractV2Error
        ):
            build_body_sway_dynamic_seam_bundle_contract_v2(source, attack)

    def test_missing_extra_wrong_address_and_mutated_bytes_fail_closed(self):
        source, probe = _documents()
        with tempfile.TemporaryDirectory() as temporary, \
                _validated_documents():
            root = Path(temporary)
            published = BodySwayDynamicSeamBundleStoreV2(root).publish(
                source, probe,
            )
            reader = BodySwayDynamicSeamBundleReaderV2(root)
            with self.assertRaises(BodySwayDynamicSeamBundleReaderV2Error):
                reader.load(
                    "fixture-project", "f" * 64,
                    published.bundle_sha256,
                )
            extra = published.path / "latest.json"
            extra.write_text("{}", encoding="utf-8")
            with self.assertRaises(BodySwayDynamicSeamBundleReaderV2Error):
                reader.load(
                    "fixture-project", published.probe_sha256,
                    published.bundle_sha256,
                )
            extra.unlink()
            target = published.path / DOCUMENT_NAMES[2]
            target.write_bytes(b"{}")
            with self.assertRaises(BodySwayDynamicSeamBundleReaderV2Error):
                reader.load(
                    "fixture-project", published.probe_sha256,
                    published.bundle_sha256,
                )

    def test_invalid_documents_do_not_create_bundle_hierarchy(self):
        source, probe = _documents()
        probe["status"] = "forged"
        with tempfile.TemporaryDirectory() as temporary, \
                _validated_documents():
            root = Path(temporary)
            before = tuple(root.iterdir())
            with self.assertRaises(BodySwayDynamicSeamBundleStoreV2Error):
                BodySwayDynamicSeamBundleStoreV2(root).publish(source, probe)
            after = tuple(root.iterdir())
        self.assertEqual(before, after)

    def test_historical_reader_has_no_discovery_or_current_head_authority(self):
        source = (SRC / "autospine_workbench" /
                  "body_sway_dynamic_seam_bundle_reader_v2.py").read_text(
                      encoding="utf-8"
                  )
        for forbidden in (
            ".glob(", ".rglob(", "latest_for_", "read_latest",
            "current_head",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
