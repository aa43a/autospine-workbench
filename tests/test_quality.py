"""Repository-level maintainability ratchets."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "src", ROOT / "web")
SOURCE_SUFFIXES = {".py", ".js", ".css", ".html"}
DEFAULT_MAX_LINES = 400

# Current ratchet ceilings. Entries may only be lowered or removed.
LEGACY_MAX_LINES = {
    "src/autospine_workbench/project_store.py": 838,
    "web/app.js": 1182,
    "web/styles.css": 1713,
}


def source_files() -> list[Path]:
    return sorted(
        path
        for root in SOURCE_ROOTS
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and "__pycache__" not in path.parts
    )


def physical_line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


class SourceQualityBudgetTests(unittest.TestCase):
    def test_source_files_respect_line_budgets(self) -> None:
        violations: list[str] = []
        for path in source_files():
            relative = path.relative_to(ROOT).as_posix()
            limit = LEGACY_MAX_LINES.get(relative, DEFAULT_MAX_LINES)
            actual = physical_line_count(path)
            if actual > limit:
                violations.append(f"{relative}: {actual} lines > {limit}")
        self.assertEqual([], violations, "\n".join(violations))

    def test_legacy_allowlist_contains_only_oversized_source(self) -> None:
        stale: list[str] = []
        for relative in LEGACY_MAX_LINES:
            path = ROOT / relative
            if not path.is_file():
                stale.append(f"{relative}: file no longer exists")
            elif physical_line_count(path) <= DEFAULT_MAX_LINES:
                stale.append(f"{relative}: now fits the default budget; remove allowlist entry")
        self.assertEqual([], stale, "\n".join(stale))


if __name__ == "__main__":
    unittest.main()
