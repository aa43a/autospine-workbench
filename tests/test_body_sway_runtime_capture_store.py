"""Content-addressed body-sway runtime capture bundle/store tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture import (  # noqa: E402
    BodySwayRuntimeCapture,
    compile_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_bundle import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    MANIFEST_NAME,
    body_sway_runtime_capture_bundle_sha256,
    build_body_sway_runtime_capture_bundle,
)
from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_store import (  # noqa: E402
    NAMESPACE,
    BodySwayRuntimeCaptureStore,
    BodySwayRuntimeCaptureStoreError,
)
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class BodySwayRuntimeCaptureStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        inputs = cls.root / "inputs"
        inputs.mkdir()
        cls.fixture = RuntimeCaptureFixture(inputs)
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(cls.fixture.sessions)
            image = capture_png()
            for case_id in collector.case_ids:
                collector.record_capture(case_id, image, device_pixel_ratio=1)
            browser = BrowserExecutableSnapshot(
                path=str(cls.root / "chrome.exe"),
                family="chromium",
                reported_version="128.0.6613.0",
                version_output_sha256=hashlib.sha256(
                    b"Chromium 128.0.6613.0\n"
                ).hexdigest(),
                executable_sha256="b" * 64,
                size_bytes=4096,
            )
            cls.capture = compile_body_sway_runtime_capture(
                cls.fixture.preview, cls.fixture.runtime,
                cls.fixture.sessions, collector.snapshot(), browser,
            )
            cls.bundle = build_body_sway_runtime_capture_bundle(cls.capture)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def store(self, name: str = "state") -> BodySwayRuntimeCaptureStore:
        return BodySwayRuntimeCaptureStore(self.root / name)

    def publish(self, store: BodySwayRuntimeCaptureStore):
        with fake_runtime_profile():
            return store.publish(self.capture)

    def test_bundle_domain_framing_is_deterministic_and_order_sensitive(self):
        with fake_runtime_profile():
            second = build_body_sway_runtime_capture_bundle(self.capture)
        self.assertEqual(self.bundle, second)
        self.assertIsInstance(BUNDLE_ADDRESS_DOMAIN, bytes)
        self.assertNotEqual(self.capture.sha256, self.bundle.bundle_sha256)
        self.assertNotEqual(
            self.capture.artifact_set_sha256, self.bundle.bundle_sha256
        )
        items = self.bundle.file_items[1:]
        reversed_sha = body_sway_runtime_capture_bundle_sha256(
            self.bundle.manifest_bytes, tuple(reversed(items))
        )
        changed_manifest_sha = body_sway_runtime_capture_bundle_sha256(
            self.bundle.manifest_bytes + b"\n", items
        )
        self.assertNotEqual(self.bundle.bundle_sha256, reversed_sha)
        self.assertNotEqual(self.bundle.bundle_sha256, changed_manifest_sha)

    def test_publish_reuse_exact_path_and_fixed_inventory(self):
        store = self.store()
        first = self.publish(store)
        second = self.publish(store)
        expected = (
            self.root / "state" / "builds" / self.bundle.project_id /
            NAMESPACE / self.bundle.temporary_preview_sha256 /
            self.bundle.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(
            {MANIFEST_NAME, "captures"},
            {item.name for item in expected.iterdir()},
        )
        expected_pngs = {
            Path(path).name for path, _data in self.bundle.file_items[1:]
        }
        self.assertEqual(
            expected_pngs,
            {item.name for item in (expected / "captures").iterdir()},
        )
        self.assertFalse((expected.parent / "latest").exists())
        with self.assertRaises(FrozenInstanceError):
            first.path = Path("changed")  # type: ignore[misc]

    def test_store_does_not_persist_runtime_browser_or_callback_reports(self):
        published = self.publish(self.store("minimal"))
        relative_files = {
            item.relative_to(published.path).as_posix()
            for item in published.path.rglob("*") if item.is_file()
        }
        self.assertEqual(
            {name for name, _data in self.bundle.file_items}, relative_files
        )
        forbidden = {"runtime", "browser", "callback", "session", "report"}
        for path in relative_files:
            if path == MANIFEST_NAME:
                continue
            self.assertFalse(any(word in path.casefold() for word in forbidden))

    def test_concurrent_publications_converge_without_overwrite(self):
        store = self.store("concurrent")
        with fake_runtime_profile(), ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: store.publish(self.capture), range(16)))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))
        self.assertEqual(
            {self.bundle.bundle_sha256},
            {item.name for item in results[0].path.parent.iterdir()},
        )

    def test_reuse_rejects_missing_extra_wrong_type_and_changed_bytes(self):
        def changed_manifest(root):
            path = root / MANIFEST_NAME
            path.write_bytes(path.read_bytes() + b"\n")

        def changed_png(root):
            path = next((root / "captures").iterdir())
            raw = path.read_bytes()
            path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))

        mutations = (
            changed_manifest,
            changed_png,
            lambda root: (root / "extra.txt").write_bytes(b"foreign"),
            lambda root: (root / "captures" / "extra.png").write_bytes(b"x"),
            lambda root: (root / MANIFEST_NAME).unlink(),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                store = self.store(f"tamper-{index}")
                published = self.publish(store)
                mutate(published.path)
                with self.assertRaises(BodySwayRuntimeCaptureStoreError):
                    self.publish(store)

        store = self.store("wrong-type")
        published = self.publish(store)
        manifest = published.path / MANIFEST_NAME
        manifest.unlink()
        manifest.mkdir()
        with self.assertRaises(BodySwayRuntimeCaptureStoreError):
            self.publish(store)

    def test_case_aliases_hierarchy_aliases_and_symlinks_fail_closed(self):
        store = self.store("wrong-case-file")
        published = self.publish(store)
        source = published.path / MANIFEST_NAME
        middle = published.path / "renaming"
        source.rename(middle)
        middle.rename(published.path / MANIFEST_NAME.upper())
        with self.assertRaises(BodySwayRuntimeCaptureStoreError):
            self.publish(store)

        store = self.store("wrong-case-path")
        published = self.publish(store)
        namespace = published.path.parents[1]
        middle = namespace.parent / "renaming"
        namespace.rename(middle)
        middle.rename(namespace.parent / NAMESPACE.upper())
        with self.assertRaises(BodySwayRuntimeCaptureStoreError):
            self.publish(store)

        real = self.root / "real-state"
        real.mkdir()
        alias = self.root / "alias-state"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError:
            return
        try:
            with self.assertRaises(BodySwayRuntimeCaptureStoreError):
                self.publish(BodySwayRuntimeCaptureStore(alias))
        finally:
            alias.unlink()

    def test_conflicting_exact_address_is_never_overwritten(self):
        parent = (
            self.root / "conflict" / "builds" / self.bundle.project_id /
            NAMESPACE / self.bundle.temporary_preview_sha256
        )
        destination = parent / self.bundle.bundle_sha256
        destination.mkdir(parents=True)
        marker = destination / "owner.txt"
        marker.write_text("foreign", encoding="utf-8")
        with self.assertRaises(BodySwayRuntimeCaptureStoreError):
            self.publish(self.store("conflict"))
        self.assertEqual("foreign", marker.read_text(encoding="utf-8"))

    def test_invalid_input_creates_no_state(self):
        root = self.root / "invalid"
        with self.assertRaises(BodySwayRuntimeCaptureStoreError):
            BodySwayRuntimeCaptureStore(root).publish({})  # type: ignore[arg-type]
        self.assertFalse(root.exists())

        noncanonical_root = self.root / "noncanonical"
        forged = BodySwayRuntimeCapture(
            self.capture.canonical_bytes.decode("utf-8") + " ",
            tuple(self.capture.capture_bytes.items()),
        )
        with fake_runtime_profile(), self.assertRaises(
            BodySwayRuntimeCaptureStoreError
        ):
            BodySwayRuntimeCaptureStore(noncanonical_root).publish(forged)
        self.assertFalse(noncanonical_root.exists())


if __name__ == "__main__":
    unittest.main()
