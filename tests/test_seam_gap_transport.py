import unittest
from autospine_workbench.targets.spine43.seam_gap_transport import predict, compare


class TransportTests(unittest.TestCase):
    def test_tied_triangles_cannot_choose_convenient_motion(self):
        source = [[0,0],[10,0],[0,10]] * 2
        target = source[:3] + [[20,0],[30,0],[20,10]]
        self.assertIsNone(predict([2,3], source, target, [0,1,2,3,4,5]))

    def test_translation_and_rotation(self):
        source = [[0,0],[10,0],[0,10]]
        self.assertEqual(predict([2,3], source, [[20,0],[20,10],[10,0]], [0,1,2]), [17,2])

    def test_distance_and_nonfinite_rejected(self):
        source = [[0,0],[10,0],[0,10]]
        self.assertIsNone(predict([30,30], source, source, [0,1,2]))
        with self.assertRaises(ValueError): predict([float('nan'),0],source,source,[0,1,2])
        with self.assertRaises(ValueError): predict([0,0],[[0,0]]*3,source,[0,1,2])

    def test_dual_attachment_disagreement(self):
        source = [[0,0],[10,0],[0,10]]; moved = [[20,0],[30,0],[20,10]]
        a={'frame':0,'centroid':[2,3]}; b={'frame':1,'centroid':[22,3]}
        attachments={n:{n:{'triangles':[0,1,2]}} for n in ('a','b')}
        poses=[{'a':source,'b':source},{'a':moved,'b':moved}]
        self.assertAlmostEqual(compare(a,b,poses,attachments,('a','b'))['distance'],0)
        poses[1]['b']=source
        self.assertEqual(compare(a,b,poses,attachments,('a','b'))['status'],'attachment_motion_disagreement')
