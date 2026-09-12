from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import patch
import math
import unittest
from autospine_workbench.targets.character43.projected_lengths import build
from autospine_workbench.targets.character43.affine_pose import matrices


def projection():
    frames = []
    for tick, points in [(0, [(0, 0, 0), (0, 1, 0), (0, 2, 0)]),
                         (1000000, [(0, 0, 0), (0, .8, .6), (0, 1.4, 1.4)])]:
        frames.append(NS(tick=tick, joints=[(n, NS(world_xyz=p, screen_xy=p[:2]))
                                           for n, p in zip(('a', 'b', 'c'), points)]))
    return NS(frames=frames, source_sha256='a'*64, map_sha256='b'*64)


class LengthTests(unittest.TestCase):
    def test_child_length_and_thickness_do_not_multiply_parent_scale(self):
        doc = dict(bones=[dict(name='upperarm_l', x=0, y=0, rotation=0),
                          dict(name='forearm_l', parent='upperarm_l', x=10, y=0, rotation=60)],
                   animations={'walk': {'bones': {}}})
        before = deepcopy(doc)
        mapping = {'bones': [dict(role='humanoid.arm.'+role+'.left', joint_name=a,
                                  aim=dict(kind='joint', joint_name=b))
                             for role, a, b in [('upper', 'a', 'b'), ('lower', 'b', 'c')]]}
        with patch('autospine_workbench.targets.character43.projected_lengths.project_bvh_frames', return_value=projection()):
            result, evidence = build(doc, 'walk', None, mapping)
        self.assertEqual(doc, before)
        for name, expected in [('upperarm_l', .8), ('forearm_l', .6)]:
            a, b, c, d, _, _ = matrices(result, 'walk', 1)[name]
            self.assertAlmostEqual(math.hypot(a, c), expected)
            self.assertAlmostEqual((a*d-b*c)/math.hypot(a, c), 1)
        self.assertEqual(evidence['status'], 'preview_only')

    def test_collapsed_projection_is_not_clamped_into_validity(self):
        data = projection()
        data.frames[1].joints[1][1].screen_xy = (0, .001)
        mapping = {'bones': [dict(role='humanoid.arm.upper.left', joint_name='a',
                                  aim=dict(kind='joint', joint_name='b'))]}
        with patch('autospine_workbench.targets.character43.projected_lengths.project_bvh_frames', return_value=data):
            with self.assertRaisesRegex(ValueError, 'collapsed'):
                build({}, 'walk', None, mapping)
