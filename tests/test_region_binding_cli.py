"""Source closure and stable replays for the layer binding entry point."""
import json
import unittest

from tests import test_benchmark_assisted_skeleton_cli as fixtures
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.benchmark.region_binding_cli import read_region_bindings
from autospine_workbench.resolved_project import canonical_sha256


class RegionBindingCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistedSkeletonCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f

    def build(self, reviewed=True):
        skeleton = self.fixture.build(self.fixture.annotations(reviewed=reviewed))[0]
        path = self.f.root/'skeleton.json'
        path.write_text(json.dumps(skeleton), encoding='utf-8')
        args = ['--state-root', self.f.state, 'build-region-bindings', '--manifest',
                self.f.root/'manifest.json', '--workspace', self.f.root, '--skeleton', path,
                '--html', self.f.root/'bindings.html']
        parsed = parser().parse_args(list(map(str, args)))
        result = _execute(parsed)
        self.assertEqual(_execute(parsed), result)
        return result

    def test_source_bound_replay_and_source_change_rejected(self):
        doc, _, _, code = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(len(doc['bindings']), len(self.f.candidate['layers']))
        self.assertFalse(doc['production_authorized'])
        self.assertEqual(read_region_bindings(self.f.state, self.f.manifest,
                         canonical_sha256(doc), workspace=self.f.root), doc)
        html = (self.f.root/'bindings.html').read_text('utf-8')
        self.assertIn('data:image/png;base64,', html)
        self.assertNotIn(str(self.f.root), html)
        (self.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_region_bindings(self.f.state, self.f.manifest, canonical_sha256(doc), workspace=self.f.root)

    def test_blocked_skeleton_has_no_options(self):
        doc, _, _, code = self.build(reviewed=False)
        self.assertEqual(code, 2)
        self.assertEqual(doc['status'], 'blocked')
        self.assertTrue(all(not row['bone_options'] for row in doc['bindings']))
