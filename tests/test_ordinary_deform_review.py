"""Each side reports its own QA rather than inheriting the candidate's status."""
import unittest
from html.parser import HTMLParser

from test_ordinary_sleeve_deform import sources
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build
from autospine_workbench.asset.planning.ordinary_sleeve_deform_review import render
from autospine_workbench.asset.planning.component_temporal_qa import passed


class OrdinaryDeformReviewTests(unittest.TestCase):
    def test_before_and_after_have_independent_failure_counts(self):
        repair, source, draft, skeleton = sources(True)
        document = build(repair, source, draft, skeleton)
        page = render(document, repair=repair, source=source, draft=draft, skeleton=skeleton)
        row = document['records'][0]
        before = sum(not passed(q) for track in row['tracks'] for q in track['before_qa'])
        after = sum(not passed(q) for track in row['tracks'] for q in track['qa'])
        self.assertIn(f'本侧离散检查：{before} 个失败姿态', page)
        self.assertIn(f'本侧离散检查：{after} 个失败姿态', page)
        self.assertIn('最新结果请查看工作台任务报告', page)
        self.assertNotIn('尚未验证目标插值、接缝或官方Runtime', page)
        HTMLParser().feed(page)
