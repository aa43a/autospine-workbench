import unittest
from autospine_workbench.targets.character43.attachment_root_transport import displacements


class RootTransportTests(unittest.TestCase):
    def test_root_uses_owner_warp_and_descendants_translate_without_scaling(self):
        bones = [dict(name='root'), dict(name='chest', parent='root'),
                 dict(name='cloth', parent='root'), dict(name='tip', parent='cloth')]
        old = dict(root=(1,0,0,1,0,0), chest=(1,0,0,1,10,20),
                   cloth=(0,-1,1,0,14,22), tip=(0,-1,1,0,14,32))
        new = dict(old, chest=(.5,0,0,1,11,23))
        shifts = displacements(bones, old, new, 'chest', ['cloth'])
        self.assertEqual(shifts, dict(cloth=(-1,3), tip=(-1,3)))
        self.assertEqual(old['tip'], (0,-1,1,0,14,32))

    def test_owner_descendant_and_overlapping_roots_are_rejected(self):
        bones = [dict(name='root'), dict(name='chest',parent='root'),
                 dict(name='arm',parent='chest'), dict(name='cloth',parent='root'),
                 dict(name='tip',parent='cloth')]
        for roots in (['arm'], ['cloth','tip']):
            with self.assertRaises(ValueError):
                displacements(bones, {}, {}, 'chest', roots)


if __name__ == '__main__':
    unittest.main()
