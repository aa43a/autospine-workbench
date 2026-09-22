import unittest
from m4_clip_correspondence import build


def row(time,points,keys):
    return dict(time=time,status='single_loop',loops=[dict(points=points,vertex_keys=keys)])


class CorrespondenceTests(unittest.TestCase):
    def test_inserted_collinear_vertex_preserves_anchor_positions(self):
        a=row(0,[[0,0],[2,0],[0,2]],[['v',0],['v',1],['v',2]])
        b=row(1,[[0,0],[1,0],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        result=build([a,b]);self.assertEqual(result['frames'][0]['points'],result['frames'][1]['points'])
        self.assertEqual(result['maximum_sampled_boundary_error_px'],0)

    def test_winding_change_rejected(self):
        a=row(0,[[0,0],[2,0],[0,2]],[['v',0],['v',1],['v',2]])
        b=row(1,[[0,0],[0,2],[2,0]],[['v',0],['v',2],['v',1]])
        with self.assertRaisesRegex(ValueError,'order'):build([a,b])

    def test_budget_not_silently_relaxed(self):
        a=row(0,[[0,0],[1,-1],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        with self.assertRaisesRegex(ValueError,'budget'):build([a],limit=3)

    def test_moving_short_corner_keeps_error_bounded(self):
        keys=[['v',0],['e',0,1],['v',1],['v',2]]
        rows=[row(t,[[0,0],[x,-.5],[10,0],[0,10]],keys) for t,x in enumerate([.2,.3,.4])]
        result=build(rows,tolerance=.1,limit=50)
        self.assertLessEqual(result['maximum_sampled_boundary_error_px'],.1)
        self.assertLessEqual(result['vertex_count'],50)

    def test_nonfinite_points_rejected(self):
        with self.assertRaisesRegex(ValueError,'input'):
            build([row(0,[[0,0],[float('nan'),1],[1,0]],[['v',0],['v',1],['v',2]])])
