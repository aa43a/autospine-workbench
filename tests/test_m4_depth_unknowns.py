import unittest
from m4_depth_unknowns import locate


class DepthUnknownTests(unittest.TestCase):
    def fixture(self):
        mesh = dict(uvs=[0,0,1,0,0,1], triangles=[0,1,2],
                    vertices=[1,0,0,0,1, 1,1,0,0,1, 1,0,1,0,1])
        doc = dict(bones=[dict(name='hand_r'),dict(name='cloth',parent='forearm_r')],
                   skins=[dict(attachments={'arm':{'arm':mesh}})])
        field = dict(candidate='id', arm='arm', rows=[
            dict(time=i, depth_values=[1, value, -1])
            for i,value in enumerate([None,None,0,None])])
        return doc, field

    def test_unknown_runs_keep_gap_and_helper_identity(self):
        report = locate(*self.fixture())
        self.assertEqual(report['unknown_vertex_samples'], 3)
        self.assertEqual(report['unknown_vertices'], 1)
        self.assertEqual([r['sample_count'] for r in report['issues']], [2,1])
        self.assertEqual(report['issues'][0]['influences'][0]['bone'], 'cloth')
        self.assertEqual(report['issues'][0]['triangles'], [0])
        self.assertFalse(report['selected'])

    def test_invalid_samples_are_not_available_depth(self):
        for bad in (float('nan'), float('inf')):
            doc, field = self.fixture()
            field['rows'][0]['depth_values'][1] = bad
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                locate(doc, field)

    def test_reversed_time_rejected(self):
        doc, field = self.fixture()
        field['rows'].reverse()
        with self.assertRaisesRegex(ValueError, 'schedule'):
            locate(doc, field)

    def test_axis_evidence_does_not_fill_unknown_depth(self):
        doc, field = self.fixture()
        doc['skins'][0]['attachments']['arm']['arm']['vertices'][7] = -3
        report = locate(doc, field, axis_lengths={'cloth': 10})
        influence = report['issues'][0]['influences'][0]
        self.assertEqual(influence['axis_ratio'], -.3)
        self.assertTrue(influence['outside_quarter_cap'])
        self.assertEqual(report['unknown_vertices'], 1)
