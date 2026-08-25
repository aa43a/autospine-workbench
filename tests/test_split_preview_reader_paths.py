"""Portable path-boundary tests for immutable split preview reads."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.split_preview_reader import (  # noqa: E402
    SplitPreviewReader,
    SplitPreviewReaderError,
)


DIGEST = "a" * 64


class SplitPreviewReaderPathTests(unittest.TestCase):
    def test_windows_device_names_and_trailing_aliases_are_invalid_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reader = SplitPreviewReader(Path(directory))
            aliases = (
                "CON",
                "con",
                "Con.preview",
                "NUL",
                "nul.json",
                "PRN",
                "AUX",
                "COM1",
                "com9.preview",
                "LPT1",
                "lpt9.preview",
                "project.",
                "project ",
            )
            for project_id in aliases:
                with self.subTest(project_id=project_id), self.assertRaisesRegex(
                    SplitPreviewReaderError, "identity"
                ):
                    reader.load(project_id, DIGEST)

    def test_case_aliased_path_components_fail_closed(self) -> None:
        cases = (
            ("Analysis", "CaseProject", "split-previews", f"{DIGEST}.json", "CaseProject"),
            ("analysis", "CaseProject", "split-previews", f"{DIGEST}.json", "caseproject"),
            ("analysis", "CaseProject", "Split-Previews", f"{DIGEST}.json", "CaseProject"),
            ("analysis", "CaseProject", "split-previews", f"{DIGEST.upper()}.json", "CaseProject"),
        )
        for analysis, stored_project, kind, filename, requested_project in cases:
            with self.subTest(
                analysis=analysis,
                project=stored_project,
                kind=kind,
                filename=filename,
            ), tempfile.TemporaryDirectory() as directory:
                state = Path(directory)
                artifact = state / analysis / stored_project / kind / filename
                artifact.parent.mkdir(parents=True)
                artifact.write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(SplitPreviewReaderError, "unsafe"):
                    SplitPreviewReader(state).load(requested_project, DIGEST)

    def test_symlink_project_component_fails_closed_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            analysis = state / "analysis"
            analysis.mkdir()
            target = state / "target-project"
            target.mkdir()
            link = analysis / "LinkedProject"
            try:
                os.symlink(target, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            with self.assertRaisesRegex(SplitPreviewReaderError, "unsafe"):
                SplitPreviewReader(state).load("LinkedProject", DIGEST)

    @unittest.skipUnless(
        os.name == "nt" and hasattr(Path("."), "is_junction"),
        "Windows junction detection is unavailable",
    )
    def test_windows_junction_project_component_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            analysis = state / "analysis"
            analysis.mkdir()
            target = state / "junction-target"
            target.mkdir()
            junction = analysis / "JunctionProject"
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"junction creation unavailable: {created.stderr.strip()}")
            try:
                self.assertTrue(junction.is_junction())
                with self.assertRaisesRegex(SplitPreviewReaderError, "unsafe"):
                    SplitPreviewReader(state).load("JunctionProject", DIGEST)
            finally:
                junction.rmdir()


if __name__ == "__main__":
    unittest.main()
