from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.state_root_preflight import (  # noqa: E402
    StateRootMutationUnavailable,
    preflight_state_root_mutations,
)


class StateRootPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "state"
        self.project = self.root / "builds" / "sample-project"
        self.project.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inventory(self) -> tuple[str, ...]:
        return tuple(sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
        ))

    def test_success_exercises_root_and_project_without_residue(self) -> None:
        before = self.inventory()

        preflight_state_root_mutations(self.root, ("sample-project",))

        self.assertEqual(self.inventory(), before)

    def test_mkdir_denial_is_path_free_and_fail_closed(self) -> None:
        with patch(
            "autospine_workbench.state_root_preflight.os.mkdir",
            side_effect=PermissionError(13, "private path"),
        ):
            with self.assertRaises(StateRootMutationUnavailable) as caught:
                preflight_state_root_mutations(self.root, ("sample-project",))
        self.assertNotIn(str(self.root), str(caught.exception))
        self.assertEqual(self.inventory(), ("builds", "builds/sample-project"))

    def test_missing_hard_link_support_cleans_the_probe(self) -> None:
        with patch(
            "autospine_workbench.state_root_preflight.os.link",
            side_effect=OSError("hard links unavailable"),
        ):
            with self.assertRaises(StateRootMutationUnavailable):
                preflight_state_root_mutations(self.root, ("sample-project",))
        self.assertEqual(self.inventory(), ("builds", "builds/sample-project"))


if __name__ == "__main__":
    unittest.main()
