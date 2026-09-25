import unittest
from m4_runtime_batch_player import viewport


class BatchPlayerTests(unittest.TestCase):
    def test_union_contains_later_frames_not_only_first_batch(self):
        first=dict(left=207,bottom=-1036,width=575,height=1135)
        later=dict(left=181,bottom=-1037,width=610,height=1138)
        self.assertEqual(viewport([first,later]),later)

    def test_invalid_or_empty_viewport_is_rejected(self):
        for infos in ([],[dict(left=0,bottom=0,width=-1,height=1)],
                      [dict(left=float('nan'),bottom=0,width=1,height=1)]):
            with self.assertRaises(ValueError):viewport(infos)


if __name__=='__main__':unittest.main()
