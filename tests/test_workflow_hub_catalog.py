"""Keep the workflow hub synchronized with executable and documented features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import build_parser  # noqa: E402


CATALOG_PATH = ROOT / "web" / "workflow-catalog.json"


def parser_commands() -> set[str]:
    parser = build_parser()
    actions = (
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return set(next(actions).choices)


class WorkflowHubCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.entries = cls.catalog["entries"]

    def test_catalog_has_one_entry_for_every_cli_command(self) -> None:
        commands = parser_commands()
        catalog_commands = {
            entry["command"] for entry in self.entries
            if entry["kind"] == "cli"
        }
        self.assertEqual(76, len(commands))
        self.assertEqual(commands, catalog_commands)

    def test_entries_have_unique_ids_and_supported_taxonomy(self) -> None:
        ids = [entry["id"] for entry in self.entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(108, len(ids))
        self.assertEqual(
            {"cli": 76, "page": 14, "planned": 18},
            {
                kind: sum(entry["kind"] == kind for entry in self.entries)
                for kind in ("cli", "page", "planned")
            },
        )
        stages = {stage["id"] for stage in self.catalog["stages"]}
        for entry in self.entries:
            with self.subTest(entry=entry["id"]):
                self.assertIn(entry["kind"], {"page", "cli", "planned"})
                self.assertIn(
                    entry["status"],
                    {"available", "external_required", "planned"},
                )
                self.assertIn(entry["stage"], stages)
                self.assertTrue(entry["title"].strip())
                self.assertTrue(entry["summary"].strip())

    def test_every_document_link_is_local_and_exists(self) -> None:
        for entry in self.entries:
            with self.subTest(entry=entry["id"]):
                relative = Path(entry["doc"])
                self.assertFalse(relative.is_absolute())
                self.assertNotIn("..", relative.parts)
                self.assertTrue((ROOT / relative).is_file(), relative)

    def test_page_entries_target_all_existing_workbench_pages(self) -> None:
        expected = {
            "./index.html",
            "./motions.html",
            "./body-sway-probe.html",
            "./body-sway-review-admission-v2.html",
            "./body-sway-review.html",
            "./body-sway-review-v2.html",
            "./body-sway-runtime-capture.html",
            "./body-sway-safety-analysis-v2.html",
            "./body-sway-dynamic-seam-v2.html",
            "./motion-instance-v3-v2.html",
            "./spine42-v3-v2.html",
            "./idle-behavior-review.html",
            "./motion-policy-review.html",
            "./seam-anchor-review.html",
        }
        pages = {entry["href"] for entry in self.entries
                 if entry["kind"] == "page"}
        self.assertEqual(expected, pages)
        for href in pages:
            self.assertTrue((ROOT / "web" / href.removeprefix("./")).is_file())

    def test_current_stage_names_product_preview_and_preserves_exact_entries(self) -> None:
        self.assertEqual(
            "workbench-animated-preview-v1",
            self.catalog["current_stage"],
        )
        entry = next(
            entry for entry in self.entries
            if entry["id"] == "page-body-sway-review-v2"
        )
        self.assertEqual("./body-sway-review-v2.html", entry["href"])
        self.assertIn("不显示或填写 SHA", entry["summary"])
        admission = next(
            entry for entry in self.entries
            if entry["id"] == "page-body-sway-review-admission-v2"
        )
        self.assertEqual("./body-sway-review-admission-v2.html", admission["href"])
        self.assertIn("无需选择文件或填写 SHA", admission["summary"])
        self.assertIn("发布门禁仍阻塞", admission["summary"])
        safety = next(
            entry for entry in self.entries
            if entry["id"] == "page-body-sway-safety-analysis-v2"
        )
        self.assertEqual("./body-sway-safety-analysis-v2.html", safety["href"])
        self.assertIn("九档离散结构点", safety["summary"])
        self.assertIn("安全范围明确不可用", safety["summary"])
        seam = next(
            entry for entry in self.entries
            if entry["id"] == "page-body-sway-dynamic-seam-v2"
        )
        self.assertEqual("./body-sway-dynamic-seam-v2.html", seam["href"])
        self.assertIn("safety_run_id", seam["summary"])
        self.assertIn("无需选择项目、文件或填写 SHA", seam["summary"])
        motion_page = next(
            entry for entry in self.entries
            if entry["id"] == "page-motion-instance-v3-v2"
        )
        self.assertEqual("./motion-instance-v3-v2.html", motion_page["href"])
        self.assertIn("certified 的 P10.5d v2 完成页", motion_page["summary"])
        self.assertIn("无需选择项目、文件或填写 SHA", motion_page["summary"])
        self.assertIn("Spine adapter、Runtime、Raster 与发布权仍阻塞", motion_page["summary"])
        consumer = next(
            entry for entry in self.entries
            if entry["id"]
            == "cli-compile-body-sway-motion-consumer-admission-v2"
        )
        self.assertEqual(
            "compile-body-sway-motion-consumer-admission-v2",
            consumer["command"],
        )
        self.assertIn("无需选择文件", consumer["summary"])
        self.assertIn("不是 MotionInstance v3", consumer["summary"])
        compiler = next(
            entry for entry in self.entries
            if entry["id"]
            == "cli-compile-body-sway-motion-instance-v3-v2"
        )
        self.assertIn("P10.5d v2 probe/bundle 双 SHA", compiler["summary"])
        self.assertIn("无需选择文件", compiler["summary"])
        self.assertIn("MotionInstance v3", compiler["summary"])
        verifier = next(
            entry for entry in self.entries
            if entry["id"]
            == "cli-verify-body-sway-motion-instance-v3-v2"
        )
        self.assertIn("MotionInstance v3/bundle 双 SHA", verifier["summary"])
        self.assertIn("无需选择文件", verifier["summary"])
        spine_page = next(
            entry for entry in self.entries
            if entry["id"] == "page-spine42-v3-v2"
        )
        self.assertEqual("./spine42-v3-v2.html", spine_page["href"])
        self.assertIn("motion_run_id", spine_page["summary"])
        self.assertIn("无需选择项目、文件或填写 SHA", spine_page["summary"])
        self.assertIn("只授予 spine_adapter_emitted", spine_page["summary"])
        self.assertIn("P10.7b v1 不消费", spine_page["summary"])
        spine_compile = next(
            entry for entry in self.entries
            if entry["id"] == "cli-compile-body-sway-spine42-v3-v2"
        )
        self.assertIn("MotionInstance v3/bundle 双 SHA", spine_compile["summary"])
        self.assertIn("不选择文件", spine_compile["summary"])
        spine_verify = next(
            entry for entry in self.entries
            if entry["id"] == "cli-verify-body-sway-spine42-v3-v2"
        )
        self.assertIn("skeleton/bundle 双 SHA", spine_verify["summary"])
        self.assertIn("不选择文件或读取 current heads", spine_verify["summary"])
        next_slice = next(
            entry for entry in self.entries
            if entry["id"]
            == "planned-real-sample-spine42-v3-raster-acceptance"
        )
        self.assertIn("captured_unreviewed evidence 已交付", next_slice["summary"])
        self.assertIn("固定五份 JSON", next_slice["summary"])
        self.assertIn("四段地址 exact reader", next_slice["summary"])
        self.assertIn("guarded v2 runtime authorization 已于 4254151 交付", next_slice["summary"])
        self.assertIn("PipelineRun 与一键 Spine", next_slice["summary"])
        self.assertIn("当前没有 v2 CLI/UI", next_slice["summary"])
        self.assertIn("没有真正启动经授权的官方 Runtime", next_slice["summary"])

    def test_motion_policy_page_describes_python_preflight_without_authority(self) -> None:
        entry = next(
            entry for entry in self.entries
            if entry["id"] == "page-motion-policy-review"
        )
        self.assertIn("zero-write Python preflight", entry["summary"])
        self.assertIn("不保存、发布或自动批准", entry["summary"])
        self.assertNotIn("纯前端", entry["summary"])

    def test_motion_policy_draft_entry_stays_non_authoritative(self) -> None:
        entry = next(
            entry for entry in self.entries
            if entry["id"] == "cli-prepare-motion-policy-review-draft"
        )
        self.assertEqual("prepare-motion-policy-review-draft", entry["command"])
        self.assertIn("pending Depth proposal", entry["summary"])
        self.assertIn("草案不是批准", entry["summary"])
        self.assertIn("不生成正式 Depth policy", entry["summary"])
        self.assertEqual(
            "docs/how-to-prepare-motion-policy-review-draft.md",
            entry["doc"],
        )

    def test_planned_entries_link_only_to_the_authoritative_roadmap(self) -> None:
        planned = [entry for entry in self.entries
                   if entry["kind"] == "planned"]
        self.assertTrue(planned)
        for entry in planned:
            with self.subTest(entry=entry["id"]):
                self.assertEqual("docs/development-roadmap.md", entry["doc"])
                self.assertNotIn("command", entry)
                self.assertNotIn("href", entry)


if __name__ == "__main__":
    unittest.main()
