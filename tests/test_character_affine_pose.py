import unittest
from autospine_workbench.targets.character43.affine_pose import sample, matrices


def fixture():
    return dict(bones=[dict(name='root', x=5, y=7, rotation=0),
                       dict(name='child', parent='root', x=10, y=0, rotation=90)],
                animations={'move': {'bones': {'root': {'scale': [dict(time=0, x=1, y=1),
                                                                    dict(time=1, x=2, y=1)]}}}},
                skins=[dict(attachments={'mesh': {'mesh': {'vertices': [1, 1, 1, 0, 1]}}})])


class AffineTests(unittest.TestCase):
    def test_parent_axial_scale_preserves_rotated_child_affine_basis(self):
        doc = fixture()
        verts, pose = sample(doc, 'move', 1)
        self.assertAlmostEqual(verts['mesh'][0][0], 25)
        self.assertAlmostEqual(verts['mesh'][0][1], 8)
        self.assertAlmostEqual(pose['child'][2], 90)
        self.assertEqual(matrices(doc, 'move', 1)['root'], (2, 0, 0, 1, 5, 7))

    def test_nonuniform_scale_and_translation_interpolate(self):
        doc = fixture()
        doc['animations']['move']['bones']['root']['translate'] = [dict(time=0, x=0, y=0), dict(time=1, x=4, y=6)]
        verts, _ = sample(doc, 'move', .5)
        self.assertAlmostEqual(verts['mesh'][0][0], 22)
        self.assertAlmostEqual(verts['mesh'][0][1], 11)

    def test_unsupported_inheritance_and_zero_scale_fail(self):
        doc = fixture(); doc['bones'][1]['inherit'] = 'noScale'
        with self.assertRaisesRegex(ValueError, 'unsupported'): sample(doc, 'move', 1)
        doc = fixture(); doc['animations']['move']['bones']['root']['scale'][1]['x'] = 0
        with self.assertRaisesRegex(ValueError, 'scale'): sample(doc, 'move', 1)
