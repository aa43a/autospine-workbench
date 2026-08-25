"""Strict read-only verification tests for immutable P4 IK bundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_bundle_integrity import (  # noqa: E402
    IkBundleIntegrityError,
    IkBundleSnapshot,
    verify_ik_bundle_snapshot,
)
from autospine_workbench import ik_bundle_reader  # noqa: E402
from autospine_workbench.ik_bundle_reader import (  # noqa: E402
    VerifiedIkBundleReader,
    VerifiedIkBundleReaderError,
)
from autospine_workbench.ik_bundle_store import IkBundleStore  # noqa: E402
from autospine_workbench.ik_probe_report import build_ik_probe_report  # noqa: E402
from autospine_workbench.ik_target_profile import (  # noqa: E402
    compile_ik_target_profile,
)
from tests.test_mesh_bundle_integrity import MeshReaderFixture  # noqa: E402
from tests.test_ik_target_profile import verified_bundle  # noqa: E402


class IkReaderFixture:
    def __init__(self, root: Path, *, converted: bool = True) -> None:
        self.state = root / "state"
        self.base = verified_bundle(converted=converted)
        self.profile = compile_ik_target_profile(self.base).document
        self.probes = build_ik_probe_report(self.profile).document
        self.published = IkBundleStore(self.state).publish(
            self.base.project_id, self.profile, self.probes
        )

    @property
    def bundle(self) -> Path:
        return self.published.path

    def load(self, *, base=None):
        supplied = self.base if base is None else base
        with patch(
            "autospine_workbench.ik_bundle_integrity.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.return_value = supplied
            result = VerifiedIkBundleReader(self.state).load(
                self.base.project_id,
                self.published.profile_sha256,
                self.published.bundle_sha256,
            )
            reader.assert_called_once_with(self.state)
            reader.return_value.load.assert_called_once_with(
                self.base.project_id,
                self.base.rig_sha256,
                self.base.bundle_sha256,
            )
            return result


class IkBundleReaderSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_bundle_is_fully_rebuilt_with_frozen_isolated_accessors(self) -> None:
        fixture = IkReaderFixture(self.root)
        result = fixture.load()

        self.assertEqual(fixture.bundle.resolve(), result.path)
        self.assertEqual(fixture.base.project_id, result.project_id)
        self.assertEqual(
            fixture.published.profile_sha256, result.profile_sha256
        )
        self.assertEqual(fixture.published.bundle_sha256, result.bundle_sha256)
        self.assertEqual(fixture.base.rig_sha256, result.p3_rig_sha256)
        self.assertEqual(fixture.base.bundle_sha256, result.p3_bundle_sha256)
        self.assertEqual(("profile.json", "probes.json"), result.inventory)
        self.assertEqual("passed", result.probes["status"])
        self.assertEqual(fixture.profile["source"], result.source_identities)
        changed_profile = result.profile
        changed_source = result.source_identities
        changed_profile.clear()
        changed_source.clear()
        self.assertTrue(result.profile)
        self.assertTrue(result.source_identities)
        with self.assertRaises(FrozenInstanceError):
            result.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_reviewed_noop_p3_still_rebuilds_four_ik_handles(self) -> None:
        fixture = IkReaderFixture(self.root, converted=False)
        result = fixture.load()

        self.assertEqual([], fixture.base.rig["attachments"])
        self.assertEqual(4, len(result.profile["handles"]))
        self.assertEqual(20, result.probes["summary"]["evaluated_case_count"])

    def test_each_p4_file_is_opened_once_and_state_tree_is_unchanged(self) -> None:
        fixture = IkReaderFixture(self.root)
        before = _tree_snapshot(fixture.state)
        original = Path.open
        reads = []

        def tracked(path: Path, *args, **kwargs):
            try:
                relative = path.resolve().relative_to(
                    fixture.bundle.resolve()
                ).as_posix()
            except ValueError:
                relative = ""
            if relative:
                reads.append(relative)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", tracked):
            fixture.load()
        self.assertEqual(sorted(("profile.json", "probes.json")), sorted(reads))
        self.assertEqual(before, _tree_snapshot(fixture.state))

    def test_nested_p3_reader_call_and_rebuild_leave_state_unchanged(self) -> None:
        p3 = MeshReaderFixture(self.root, with_targets=True)
        base = verified_bundle()
        profile = compile_ik_target_profile(base).document
        probes = build_ik_probe_report(profile).document
        published = IkBundleStore(p3.state).publish(
            base.project_id, profile, probes
        )
        before = _tree_snapshot(p3.state)

        def nested_load(*_args):
            self.assertEqual(p3.published.bundle_sha256, p3.load().bundle_sha256)
            return base

        with patch(
            "autospine_workbench.ik_bundle_integrity.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.side_effect = nested_load
            result = VerifiedIkBundleReader(p3.state).load(
                base.project_id,
                published.profile_sha256,
                published.bundle_sha256,
            )

        self.assertEqual(4, len(result.profile["handles"]))
        self.assertEqual("passed", result.probes["status"])
        reader.assert_called_once_with(p3.state)
        reader.return_value.load.assert_called_once_with(
            base.project_id, base.rig_sha256, base.bundle_sha256
        )
        self.assertEqual(before, _tree_snapshot(p3.state))


class IkBundleReaderTamperTests(unittest.TestCase):
    def fixture(self, *, converted=True) -> IkReaderFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return IkReaderFixture(Path(temporary.name), converted=converted)

    def assert_rejected(self, fixture: IkReaderFixture, *, base=None) -> None:
        with self.assertRaises(VerifiedIkBundleReaderError):
            fixture.load(base=base)

    def test_wrong_identity_latest_case_mismatch_and_escape_are_rejected(self) -> None:
        fixture = self.fixture()
        reader = VerifiedIkBundleReader(fixture.state)
        cases = (
            ("../escape", fixture.published.profile_sha256, fixture.published.bundle_sha256),
            (fixture.base.project_id, "latest", fixture.published.bundle_sha256),
            (fixture.base.project_id, fixture.published.profile_sha256, "latest"),
            (fixture.base.project_id, "0" * 64, fixture.published.bundle_sha256),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                VerifiedIkBundleReaderError
            ):
                reader.load(*values)

        target_root = fixture.bundle.parent.parent
        temporary = target_root.parent / "temporary-targets"
        target_root.rename(temporary)
        temporary.rename(target_root.parent / "IK-TARGETS")
        self.assert_rejected(fixture)

    def test_missing_extra_directory_case_alias_and_resource_limits_fail(self) -> None:
        mutations = (
            lambda bundle: (bundle / "probes.json").unlink(),
            lambda bundle: (bundle / "extra.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "nested").mkdir(),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

        fixture = self.fixture()
        source = fixture.bundle / "profile.json"
        temporary = source.with_name("temporary.json")
        source.rename(temporary)
        temporary.rename(source.with_name("PROFILE.JSON"))
        self.assert_rejected(fixture)

        fixture = self.fixture()
        with patch(
            "autospine_workbench.ik_bundle_reader.MAX_DOCUMENT_BYTES", 1
        ):
            self.assert_rejected(fixture)
        with patch(
            "autospine_workbench.ik_bundle_reader.MAX_TOTAL_DOCUMENT_BYTES", 1
        ):
            self.assert_rejected(fixture)

    def test_bundle_directory_is_rechecked_at_snapshot_boundary(self) -> None:
        fixture = self.fixture()
        real_directory = ik_bundle_reader._real_directory

        def replaced(path, label):
            if label == "IK bundle directory":
                raise VerifiedIkBundleReaderError("replaced directory")
            return real_directory(path, label)

        with patch(
            "autospine_workbench.ik_bundle_reader._real_directory",
            side_effect=replaced,
        ) as guard:
            self.assert_rejected(fixture)
        guard.assert_any_call(fixture.bundle.resolve(), "IK bundle directory")

    def test_whitespace_duplicate_nonfinite_and_invalid_utf8_fail(self) -> None:
        def whitespace(path):
            path.write_bytes(path.read_bytes() + b"\n")

        def duplicate(path):
            raw = path.read_bytes()
            path.write_bytes(b'{"format":"forged",' + raw[1:])

        def nonfinite(path):
            raw = path.read_bytes().replace(
                b'"format_version":1', b'"format_version":NaN'
            )
            path.write_bytes(raw)

        mutations = (
            whitespace,
            duplicate,
            nonfinite,
            lambda path: path.write_bytes(b"\xff"),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle / "probes.json")
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

    def test_profile_probe_and_exact_p3_dependency_drift_fail(self) -> None:
        def profile(fixture):
            value = deepcopy(fixture.profile)
            value["source"]["bundle_sha256"] = "f" * 64
            _canonical_write(fixture.bundle / "profile.json", value)

        def probes(fixture):
            value = deepcopy(fixture.probes)
            value["handles"][0]["cases"].reverse()
            _canonical_write(fixture.bundle / "probes.json", value)

        for mutate in (profile, probes):
            fixture = self.fixture()
            mutate(fixture)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

        fixture = self.fixture()
        self.assert_rejected(fixture, base=verified_bundle(identity_offset=1))

    def test_changed_profile_compiler_output_cannot_reuse_old_bundle(self) -> None:
        fixture = self.fixture()
        changed = deepcopy(fixture.profile)
        changed["canvas"]["width"] += 1
        with patch(
            "autospine_workbench.ik_bundle_integrity.compile_ik_target_profile",
            return_value=SimpleNamespace(document=changed),
        ):
            self.assert_rejected(fixture)

    def test_symlinked_file_and_state_root_are_rejected_when_supported(self) -> None:
        fixture = self.fixture()
        source = fixture.bundle / "probes.json"
        outside = fixture.bundle.parent / "outside.json"
        shutil.copyfile(source, outside)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        self.assert_rejected(fixture)

        alias = fixture.state.parent / "state-alias"
        try:
            alias.symlink_to(fixture.state, target_is_directory=True)
        except OSError:
            return
        try:
            with self.assertRaises(VerifiedIkBundleReaderError):
                VerifiedIkBundleReader(alias).load(
                    fixture.base.project_id,
                    fixture.published.profile_sha256,
                    fixture.published.bundle_sha256,
                )
        finally:
            alias.unlink()

    def test_snapshot_duplicate_and_wrong_address_fail_integrity(self) -> None:
        fixture = self.fixture()
        profile = (fixture.bundle / "profile.json").read_bytes()
        duplicate = IkBundleSnapshot(
            fixture.bundle,
            (("profile.json", profile), ("profile.json", profile)),
        )
        with self.assertRaises(IkBundleIntegrityError):
            verify_ik_bundle_snapshot(
                duplicate,
                state_root=fixture.state,
                expected_project_id=fixture.base.project_id,
                expected_profile_sha256=fixture.published.profile_sha256,
                expected_bundle_sha256=fixture.published.bundle_sha256,
            )


def _canonical_write(path: Path, value) -> None:
    path.write_bytes(json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))


def _tree_snapshot(root: Path):
    directories = tuple(sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_dir()
    ))
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }
    return directories, files


if __name__ == "__main__":
    unittest.main()
