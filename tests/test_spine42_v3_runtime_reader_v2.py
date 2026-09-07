"""Read-once and filesystem-boundary tests for P10.7b v2 evidence."""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import replace
from pathlib import Path
import pickle
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_runtime_reader_v2 as subject  # noqa: E402
from autospine_workbench import (  # noqa: E402
    spine42_v3_runtime_evidence_contract_v2 as contract,
)
from autospine_workbench.spine42_v3_runtime_evidence_v2 import (  # noqa: E402
    FIXED_NAMES, MANIFEST_NAME,
)
from autospine_workbench.spine42_v3_runtime_reader_v2 import (  # noqa: E402
    Spine42V3RuntimeReaderV2Error, Spine42V3RuntimeV2NotFound,
    VerifiedSpine42V3RuntimeEvidenceV2, VerifiedSpine42V3RuntimeReaderV2,
)
from autospine_workbench.spine42_v3_runtime_store_v2 import (  # noqa: E402
    Spine42V3RuntimeStoreV2,
)
from tests.spine42_v3_runtime_storage_v2_helpers import (  # noqa: E402
    RuntimeStorageV2Fixture, address,
)


class Spine42V3RuntimeReaderV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = RuntimeStorageV2Fixture(cls.root / "fixture")
        with cls.fixture.profile():
            cls.published = Spine42V3RuntimeStoreV2(
                cls.fixture.state_root
            ).publish(cls.fixture.evidence)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_explicit_reader_reads_upstream_once_and_each_file_once(self):
        upstream_calls, upstream_roots, file_reads = [], [], []
        real_read = subject.read_real_file

        class UpstreamSpy:
            def __init__(inner, state_root):
                upstream_roots.append(Path(state_root))

            def load(inner, *args):
                upstream_calls.append(args)
                return self.fixture.upstream

        def read_once(path, maximum, label):
            file_reads.append(Path(path))
            return real_read(path, maximum, label)

        with patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2", UpstreamSpy,
        ), patch.object(
            subject, "read_real_file", side_effect=read_once,
        ), patch.object(
            contract, "decode_rgba_png", wraps=contract.decode_rgba_png,
        ) as decode, self.fixture.profile():
            loaded = VerifiedSpine42V3RuntimeReaderV2(
                self.fixture.state_root
            ).load(*address(self.fixture.bundle))
        self.assertEqual(
            [address(self.fixture.bundle)[:3]], upstream_calls,
        )
        self.assertEqual([self.fixture.state_root], upstream_roots)
        relative = [
            path.relative_to(self.published.path).as_posix()
            for path in file_reads
        ]
        self.assertEqual(
            [name for name, _raw in self.fixture.bundle.file_items], relative,
        )
        self.assertTrue(all(count == 1 for count in Counter(relative).values()))
        capture_count = len(self.fixture.bundle.file_items) - len(FIXED_NAMES)
        self.assertEqual(capture_count, decode.call_count)
        self.assertEqual(self.fixture.bundle, loaded.bundle)
        self.assertEqual(
            (loaded.path, loaded.bundle),
            subject._require_issued_spine42_v3_runtime_reader_v2(loaded),
        )
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            replace(loaded)
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            VerifiedSpine42V3RuntimeEvidenceV2(
                loaded.path, loaded.bundle,
            )

    def test_invalid_and_missing_addresses_are_read_only(self):
        upstream_factory = Mock()
        missing = self.root / "never-created"
        with patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2", upstream_factory,
        ), self.assertRaises(Spine42V3RuntimeReaderV2Error):
            VerifiedSpine42V3RuntimeReaderV2(missing).load(
                "../bad", *address(self.fixture.bundle)[1:],
            )
        upstream_factory.assert_not_called()
        self.assertFalse(missing.exists())

        upstream = Mock()
        upstream.load.return_value = self.fixture.upstream
        with patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2",
            return_value=upstream,
        ), self.assertRaises(Spine42V3RuntimeV2NotFound):
            VerifiedSpine42V3RuntimeReaderV2(missing).load(
                *address(self.fixture.bundle)
            )
        upstream.load.assert_called_once()
        self.assertFalse(missing.exists())

    def test_missing_extra_wrong_case_and_payload_tamper_fail_closed(self):
        def root_extra(path):
            (path / "extra.bin").write_bytes(b"x")

        def fixed_missing(path):
            (path / FIXED_NAMES[1]).unlink()

        def fixed_wrong_case(path):
            source = path / FIXED_NAMES[1]
            source.rename(path / FIXED_NAMES[1].upper())

        def capture_extra(path):
            (path / "captures" / "extra.png").write_bytes(b"x")

        def capture_missing(path):
            next((path / "captures").iterdir()).unlink()

        def capture_tamper(path):
            target = next((path / "captures").iterdir())
            target.write_bytes(target.read_bytes() + b"x")

        mutations = (
            root_extra, fixed_missing, fixed_wrong_case,
            capture_extra, capture_missing, capture_tamper,
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                state, published = self._publish(mutation.__name__)
                mutation(published.path)
                with self.assertRaises(Spine42V3RuntimeReaderV2Error):
                    self._load_with_upstream(state)

    def test_symlink_boundary_fails_closed(self):
        state, published = self._publish("symlink")
        manifest = published.path / MANIFEST_NAME
        outside = self.root / "outside-manifest.json"
        outside.write_bytes(manifest.read_bytes())
        manifest.unlink()
        try:
            manifest.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            self._load_with_upstream(state)

    def test_junction_boundary_fails_closed(self):
        with patch.object(Path, "is_junction", return_value=True, create=True), \
                self.assertRaises(Spine42V3RuntimeReaderV2Error):
            self._load_with_upstream(self.fixture.state_root)

    def test_reader_has_no_mutable_head_runtime_or_browser_dependency(self):
        forbidden = (
            "require_runtime_package", "recheck_browser_executable",
            "require_current_body_sway_dynamic_seam_heads_v2",
        )
        self.assertTrue(all(name not in vars(subject) for name in forbidden))

    def test_arbitrary_copy_cannot_mint_a_verified_receipt(self):
        copied = self.root / "arbitrary-copy"
        shutil.copytree(self.published.path, copied)
        with self.fixture.profile(), self.assertRaises(
            Spine42V3RuntimeReaderV2Error,
        ):
            subject.snapshot_spine42_v3_runtime_directory_v2(
                copied, self.fixture.upstream,
            )
        with self.fixture.profile():
            bundle = subject._snapshot_spine42_v3_runtime_bundle_v2(
                copied, self.fixture.upstream, require_address=False,
            )
        self.assertIs(type(bundle), type(self.fixture.bundle))
        self.assertEqual(self.fixture.bundle, bundle)
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            VerifiedSpine42V3RuntimeEvidenceV2(copied, bundle)

    def test_receipt_copies_forgery_and_mutation_are_rejected(self):
        loaded = self._load_with_upstream(self.fixture.state_root)
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.subTest(operation=operation.__name__), \
                    self.assertRaisesRegex(TypeError, "cannot be serialized"):
                operation(loaded)
        self.assertNotIn("_READER_RECEIPT", vars(subject))
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            VerifiedSpine42V3RuntimeEvidenceV2(
                loaded.path, loaded.bundle, object(),
            )
        forged = object.__new__(VerifiedSpine42V3RuntimeEvidenceV2)
        object.__setattr__(forged, "path", loaded.path)
        object.__setattr__(forged, "bundle", loaded.bundle)
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            subject._require_issued_spine42_v3_runtime_reader_v2(forged)

        changed_path = self._load_with_upstream(self.fixture.state_root)
        object.__setattr__(changed_path, "path", self.root / "changed")
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            subject._require_issued_spine42_v3_runtime_reader_v2(changed_path)
        changed_bundle = self._load_with_upstream(self.fixture.state_root)
        object.__setattr__(changed_bundle.bundle, "clip_id", "changed")
        with self.assertRaises(Spine42V3RuntimeReaderV2Error):
            subject._require_issued_spine42_v3_runtime_reader_v2(changed_bundle)

    def _publish(self, name):
        state = self.root / f"mutated-{name}"
        with self.fixture.profile():
            published = Spine42V3RuntimeStoreV2(state).publish(
                self.fixture.evidence
            )
        return state, published

    def _load_with_upstream(self, state):
        reader = Mock()
        reader.load.return_value = self.fixture.upstream
        with patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2", return_value=reader,
        ), self.fixture.profile():
            result = VerifiedSpine42V3RuntimeReaderV2(state).load(
                *address(self.fixture.bundle)
            )
        reader.load.assert_called_once_with(*address(self.fixture.bundle)[:3])
        return result


if __name__ == "__main__":
    unittest.main()
