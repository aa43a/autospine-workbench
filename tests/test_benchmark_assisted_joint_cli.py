"""Source-bound all-point preparation and edited envelope resume."""
import json
import unittest
from tests import test_benchmark_r2a_cli as fixtures
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.benchmark.assisted_joint_cli import read_assisted_joint_draft
from autospine_workbench.resolved_project import canonical_sha256


class AssistedCliTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.R2aCliTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def run_page(self, *extra, html='assisted.html'):
        f = self.f
        args = ['--state-root', f.state, 'joint-review', '--manifest', f.root/'manifest.json',
                '--evidence', f.root/'evidence.json', '--workspace', f.root, '--character', f.candidate['character_id'],
                '--pose-observations', f.pose_path, '--html', f.root/html, *extra]
        return _execute(parser().parse_args(list(map(str, args))))[0]

    def test_prepare_resume_and_exact_read(self):
        first = self.run_page()
        self.assertEqual(len(first['draft']['records']), 17)
        self.assertEqual(first['reviewed_joint_ids'], [])
        self.assertFalse(first['independent_annotation'])
        self.assertEqual(self.run_page(), first)
        first['draft']['records'][0]['position'] = [10, 20]
        first['reviewed_joint_ids'] = ['root']
        edited = self.f.root/'edited.json'; edited.write_text(json.dumps(first), encoding='utf-8')
        result = self.run_page('--draft', edited, html='resumed.html')
        self.assertEqual(result, first)
        self.assertEqual(read_assisted_joint_draft(self.f.state, self.f.manifest, canonical_sha256(result), workspace=self.f.root), result)
        (self.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_assisted_joint_draft(self.f.state, self.f.manifest, canonical_sha256(result), workspace=self.f.root)

    def test_wrong_pose_and_claimed_independence_fail(self):
        first = self.run_page(); first['independent_annotation'] = True
        bad = self.f.root/'bad.json'; bad.write_text(json.dumps(first), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_page('--draft', bad, html='bad.html')
        pose = json.loads(self.f.pose_path.read_text()); pose['source']['image_sha256'] = '0'*64
        self.f.pose_path.write_text(json.dumps(pose), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_page(html='wrong.html')


if __name__ == '__main__':
    unittest.main()
