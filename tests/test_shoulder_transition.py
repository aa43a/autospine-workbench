import unittest

from autospine_workbench.targets.character43.shoulder_transition import append_parent
from autospine_workbench.targets.character43.affine_pose import sample


class ShoulderTransitionTests(unittest.TestCase):
    def test_sparse_deform_keeps_influence_alignment(self):
        document = dict(bones=[dict(name='chest', x=0, y=0, rotation=0),
                               dict(name='arm', x=0, y=0, rotation=0)],
            skins=[dict(attachments={'arm': {'arm': dict(vertices=[
                2, 1, 10, 0, 1., 0, 10, 0, 0., 1, 1, 20, 0, 1.])}})],
            animations={'move': dict(attachments={'default': {'arm': {'arm': dict(deform=[
                dict(time=0, offset=0, vertices=[2, 0, 100, 0, 4, 0]),
                dict(time=1, offset=4, vertices=[6, 0])])}}})})
        append_parent(document, 'arm', [.5, 0], [[10, 0], [20, 0]], 'chest')
        points, _ = sample(document, 'move', 0)
        self.assertEqual(points['arm'], [[11., 0.], [24., 0.]])
        points, _ = sample(document, 'move', 1)
        self.assertEqual(points['arm'], [[10., 0.], [26., 0.]])
        keys = document['animations']['move']['attachments']['default']['arm']['arm']['deform']
        self.assertEqual(keys[0]['vertices'], [2, 0, 100, 0, 0., 0., 4, 0])
        self.assertNotIn('offset', keys[1])


if __name__ == '__main__':
    unittest.main()
