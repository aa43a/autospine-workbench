"""Fail-closed storage tests for non-authoritative P9 review drafts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench import p9_review_draft_store as subject  # noqa: E402
from autospine_workbench.p9_review_draft_store import (  # noqa: E402
    P9ReviewDraftStoreError,
    publish_p9_review_draft,
)


PROJECT = "sample"
NAMESPACE = "wave-left-r15-draft"


def draft_files(project: str = PROJECT) -> dict[str, bytes]:
    return {
        "shared/kimodo-policy-evidence.json": b'{"kind":"evidence"}',
        f"{project}/depth-pair-policy.proposal.json": b'{"kind":"proposal"}',
        f"{project}/foot-lock-candidates.json": b'{"kind":"foot"}',
        f"{project}/draft-manifest.json": b'{"kind":"manifest"}',
    }


class P9ReviewDraftStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()

    def publish(
        self,
        *,
        state: Path | None = None,
        namespace: str = NAMESPACE,
        project: str = PROJECT,
        files: dict[str, bytes] | None = None,
    ) -> bool:
        return publish_p9_review_draft(
            state or self.state,
            namespace,
            project,
            files or draft_files(project),
        )

    @property
    def destination(self) -> Path:
        return self.state / "reviews" / NAMESPACE

    def test_real_publication_has_exact_inventory_and_reuses_exact_bytes(self):
        self.assertFalse(self.publish())
        self.assertTrue(self.publish())
        self.assertEqual(
            {"shared", PROJECT},
            {entry.name for entry in self.destination.iterdir()},
        )
        expected = draft_files()
        actual = {
            entry.relative_to(self.destination).as_posix(): entry.read_bytes()
            for entry in self.destination.rglob("*")
            if entry.is_file()
        }
        self.assertEqual(expected, actual)
        self.assertEqual(
            {NAMESPACE},
            {entry.name for entry in self.destination.parent.iterdir()},
        )

    def test_concurrent_identical_publications_have_one_destination(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: self.publish(), range(16)))
        self.assertEqual(1, sum(result is False for result in results))
        self.assertEqual(15, sum(result is True for result in results))
        self.assertEqual(
            {NAMESPACE},
            {entry.name for entry in self.destination.parent.iterdir()},
        )
        self.assertTrue(self.destination.is_dir())

    def test_reuse_rejects_changed_missing_extra_and_wrong_type_entries(self):
        def changed_bytes(root: Path) -> None:
            target = root / PROJECT / "draft-manifest.json"
            target.write_bytes(target.read_bytes() + b"\n")

        def missing_file(root: Path) -> None:
            (root / PROJECT / "foot-lock-candidates.json").unlink()

        def extra_empty_directory(root: Path) -> None:
            (root / "extra-empty").mkdir()

        def wrong_type(root: Path) -> None:
            target = root / PROJECT / "draft-manifest.json"
            target.unlink()
            target.mkdir()

        for index, mutate in enumerate((
            changed_bytes,
            missing_file,
            extra_empty_directory,
            wrong_type,
        )):
            with self.subTest(mutation=mutate.__name__):
                state = self.root / f"tamper-{index}"
                state.mkdir()
                self.assertFalse(self.publish(state=state))
                destination = state / "reviews" / NAMESPACE
                mutate(destination)
                with self.assertRaises(P9ReviewDraftStoreError):
                    self.publish(state=state)

    def test_wrong_case_and_alias_classification_fail_closed(self):
        self.assertFalse(self.publish())
        source = self.destination / PROJECT / "draft-manifest.json"
        middle = self.destination / PROJECT / "renaming"
        source.rename(middle)
        middle.rename(source.with_name("DRAFT-MANIFEST.JSON"))
        with self.assertRaises(P9ReviewDraftStoreError):
            self.publish()

        state = self.root / "classified-alias"
        state.mkdir()
        self.assertFalse(self.publish(state=state))
        project_directory = state / "reviews" / NAMESPACE / PROJECT
        real_is_alias = subject.is_alias

        def classify(path: Path) -> bool:
            return Path(path) == project_directory or real_is_alias(path)

        with patch.object(subject, "is_alias", side_effect=classify):
            with self.assertRaises(P9ReviewDraftStoreError):
                self.publish(state=state)

    def test_symlinked_state_root_fails_closed_when_supported(self):
        real = self.root / "real-state"
        real.mkdir()
        alias = self.root / "alias-state"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are unavailable")
        try:
            with self.assertRaises(P9ReviewDraftStoreError):
                self.publish(state=alias)
        finally:
            alias.unlink()

    def test_unsupported_inventory_is_rejected_without_destination(self):
        missing = draft_files()
        missing.pop(f"{PROJECT}/draft-manifest.json")
        with self.assertRaises(P9ReviewDraftStoreError):
            self.publish(files=missing)

        extra = draft_files()
        extra[f"{PROJECT}/extra.json"] = b"{}"
        with self.assertRaises(P9ReviewDraftStoreError):
            self.publish(files=extra)
        self.assertFalse(self.destination.exists())

    def test_lexical_namespace_escape_is_rejected_without_writes(self):
        escaped = self.state / "escaped"
        with self.assertRaises(P9ReviewDraftStoreError):
            self.publish(namespace="../escaped")
        self.assertFalse(escaped.exists())

    def test_unsafe_or_reserved_project_is_rejected_before_publication(self):
        for index, project in enumerate(("../escaped-project", "SHARED")):
            with self.subTest(project=project):
                state = self.root / f"invalid-project-{index}"
                state.mkdir()
                with self.assertRaises(P9ReviewDraftStoreError):
                    self.publish(
                        state=state,
                        project=project,
                        files=draft_files(project),
                    )
                self.assertFalse((state / "reviews").exists())


if __name__ == "__main__":
    unittest.main()
