from copy import deepcopy
import unittest

from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.motion_depth import _slots


class RenderRegionDepthTests(unittest.TestCase):
    def test_unused_vertex_influences_do_not_define_render_region(self):
        doc, _ = source(); candidate, _ = build(doc, ['a'])
        original = deepcopy(candidate)
        self.assertIn('a-depth-001', _slots(candidate)['other'])
        groups = _slots(candidate, render_regions=True)
        self.assertIn('a-depth-001', groups['torso'])
        self.assertIn('a-depth-003', groups['torso'])
        self.assertIn('a-depth-002', groups['other'])
        self.assertEqual(candidate, original)

    def test_even_tiny_positive_helper_influence_keeps_region_unknown(self):
        doc, _ = source(); candidate, _ = build(doc, ['a'])
        mesh = candidate['skins'][0]['attachments']['a-depth-001']['a-depth-001']
        mesh['vertices'][:5] = [2, 0, 0, 2, 1-1e-10, 1, 0, 2, 1e-10]
        self.assertIn('a-depth-001', _slots(candidate, render_regions=True)['other'])


if __name__ == '__main__':
    unittest.main()
