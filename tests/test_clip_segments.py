import unittest
from m4_clip_segments import partition
from test_clip_correspondence import row


class ClipSegmentsTests(unittest.TestCase):
    def test_topology_change_has_shared_endpoint(self):
        a=row(0,[[0,0],[2,0],[0,2]],[['v',0],['v',1],['v',2]])
        b=row(1,[[0,0],[1,0],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        report=partition([a,b]);self.assertEqual(len(report['segments']),2)
        self.assertEqual(report['joins'][0]['sampled_boundary_difference_px'],0)

    def test_curved_shared_endpoint_keeps_all_corners(self):
        a=row(0,[[0,0],[2,0],[0,2]],[['v',0],['v',1],['v',2]])
        b=row(1,[[0,0],[.3,-.07],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        c=row(2,[[0,0],[.5,-.07],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        report=partition([a,b,c])
        self.assertLess(report['joins'][0]['sampled_boundary_difference_px'],1e-12)

    def test_segment_limit_not_silently_truncated(self):
        a=row(0,[[0,0],[2,0],[0,2]],[['v',0],['v',1],['v',2]])
        b=row(1,[[0,0],[1,0],[2,0],[0,2]],[['v',0],['e',0,1],['v',1],['v',2]])
        with self.assertRaisesRegex(ValueError,'budget'):partition([a,b],segment_limit=1)
