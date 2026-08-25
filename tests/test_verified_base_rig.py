"""Fail-closed tests for the trusted P2 base bundle read boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_contract import (  # noqa: E402
    build_mesh_compile_run,
    require_mesh_compile_run,
)
from autospine_workbench.rig_bundle_integrity import (  # noqa: E402
    verify_rig_bundle_directory,
)
from autospine_workbench.verified_base_rig import (  # noqa: E402
    VerifiedBaseRigReader,
    VerifiedBaseRigReaderError,
)
from tests.test_layer_manifest import write_png  # noqa: E402
from tests.test_rig_bundle import BundleFixture  # noqa: E402


class VerifiedBaseRigReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = BundleFixture(self.root)
        self.bundle, self.rig_sha = self.fixture.publish()
        self.bundle_sha = self.bundle.name
        self.reader = VerifiedBaseRigReader(self.fixture.state)

    def load(self):
        return self.reader.load("sample-a", self.rig_sha, self.bundle_sha)

    def test_load_returns_isolated_documents_and_downstream_builder_inputs(self) -> None:
        loaded = self.load()

        self.assertEqual(self.bundle.resolve(), loaded.path)
        self.assertEqual(self.rig_sha, loaded.rig_sha256)
        self.assertEqual(self.bundle_sha, loaded.bundle_sha256)
        self.assertEqual(self.fixture.rig, loaded.rig)
        self.assertEqual(self.fixture.run, loaded.run_manifest)
        self.assertEqual(self.fixture.probes, loaded.probe_report)
        self.assertEqual("autospine-rig-setup-render", loaded.setup_document["format"])

        mesh_run = build_mesh_compile_run(
            loaded.rig,
            loaded.run_manifest,
            base_bundle_sha256=loaded.bundle_sha256,
        )
        require_mesh_compile_run(
            mesh_run,
            base_rig=loaded.rig,
            base_run=loaded.run_manifest,
            base_bundle_sha256=loaded.bundle_sha256,
        )

        documents = (
            (loaded.rig, loaded.rig),
            (loaded.run_manifest, loaded.run_manifest),
            (loaded.probe_report, loaded.probe_report),
            (loaded.setup_document, loaded.setup_document),
        )
        for first, second in documents:
            self.assertIsNot(first, second)
            first.clear()
            self.assertTrue(second)
        with self.assertRaises(FrozenInstanceError):
            loaded.rig_sha256 = "0" * 64  # type: ignore[misc]

    def test_unsafe_or_wrong_identities_fail_before_loading(self) -> None:
        cases = (
            ("../sample-a", self.rig_sha, self.bundle_sha),
            ("sample/a", self.rig_sha, self.bundle_sha),
            ("sample-a", "F" * 64, self.bundle_sha),
            ("sample-a", self.rig_sha, "latest"),
            ("SAMPLE-A", self.rig_sha, self.bundle_sha),
            ("other-project", self.rig_sha, self.bundle_sha),
            ("sample-a", "e" * 64, self.bundle_sha),
            ("sample-a", self.rig_sha, "e" * 64),
        )
        for project, rig_sha, bundle_sha in cases:
            with self.subTest(project=project, rig_sha=rig_sha, bundle=bundle_sha):
                with self.assertRaises(VerifiedBaseRigReaderError):
                    self.reader.load(project, rig_sha, bundle_sha)

    def test_project_binding_is_checked_even_at_an_existing_safe_path(self) -> None:
        other = (
            self.fixture.state
            / "builds"
            / "other-project"
            / "rig-ir"
            / self.rig_sha
            / self.bundle_sha
        )
        shutil.copytree(self.bundle, other)

        with self.assertRaises(VerifiedBaseRigReaderError):
            self.reader.load("other-project", self.rig_sha, self.bundle_sha)

    def test_verifier_returned_addresses_must_match_both_requested_hashes(self) -> None:
        actual = verify_rig_bundle_directory(self.bundle)
        for field in ("rig_sha256", "bundle_sha256"):
            changed = replace(actual, **{field: "e" * 64})
            with self.subTest(field=field), patch(
                "autospine_workbench.verified_base_rig.verify_rig_bundle_directory",
                return_value=changed,
            ):
                with self.assertRaisesRegex(
                    VerifiedBaseRigReaderError, "content address"
                ):
                    self.load()

    def test_document_png_and_inventory_tampering_fail_closed(self) -> None:
        mutations = (
            lambda bundle: (bundle / "run-manifest.json").write_text(
                "{}\n", encoding="utf-8"
            ),
            lambda bundle: write_png(
                bundle / "layers" / "layer-001-arm-l.png", 1, 1
            ),
            lambda bundle: (bundle / "unexpected.txt").write_text(
                "unexpected\n", encoding="utf-8"
            ),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index), tempfile.TemporaryDirectory() as directory:
                fixture = BundleFixture(Path(directory))
                bundle, rig_sha = fixture.publish()
                mutate(bundle)
                with self.assertRaises(VerifiedBaseRigReaderError):
                    VerifiedBaseRigReader(fixture.state).load(
                        "sample-a", rig_sha, bundle.name
                    )

    def test_bundle_symlink_escape_is_rejected_when_supported(self) -> None:
        outside = self.root / "outside-bundle"
        self.bundle.rename(outside)
        try:
            self.bundle.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            outside.rename(self.bundle)
            self.skipTest(f"directory symlink unavailable: {exc}")
        try:
            with self.assertRaisesRegex(
                VerifiedBaseRigReaderError, "unsafe|aliased"
            ):
                self.load()
        finally:
            self.bundle.unlink()


if __name__ == "__main__":
    unittest.main()
