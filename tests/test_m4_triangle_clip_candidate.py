from copy import deepcopy
import unittest
from test_clip_candidate import fixture as base_fixture
from m4_triangle_clip_candidate import build


def fixture():
    doc, _ = base_fixture()
    mesh = doc['skins'][0]['attachments']['arm']['arm']
    mesh['vertices'] = [1, 0, 0, 0, 1, 1, 0, 2, 0, 1, 1, 0, 0, 2, 1]
    report = dict(side='front', arm='arm', rows=[dict(time=t, vertices=[[0, 0], [2, 0], [0, 2]],
                                                   depth_values=v)
                        for t, v in [(0, [1, 1, -1]), (1, [-1, 1, -1])]])
    return doc, report


class TriangleClipCandidateTests(unittest.TestCase):
    def test_ordinary_clips_preserve_weighted_mesh_and_tracks(self):
        doc, field = fixture(); original = deepcopy(doc)
        candidate = build(doc, field, 'arm', 'body')
        self.assertEqual(doc, original)
        names = [s['name'] for s in candidate['slots']]
        self.assertLess(names.index('m4-tri-back-0000'), names.index('body'))
        self.assertGreater(names.index('m4-tri-front-0000'), names.index('body'))
        attachments = candidate['skins'][0]['attachments']
        for side in ('front', 'back'):
            name = f'm4-tri-{side}-0000'
            for key in ('vertices', 'triangles', 'uvs'):
                self.assertEqual(attachments[name][name][key], doc['skins'][0]['attachments']['arm']['arm'][key])
            clip = attachments[name+'-clip'][name+'-clip']
            self.assertFalse(clip['inverse']); self.assertEqual(clip['vertexCount'], 4)
            tracks = candidate['animations']['external-motion']['attachments']['default']
            self.assertEqual(tracks[name][name], doc['animations']['external-motion']['attachments']['default']['arm']['arm'])

    def test_missing_evidence_and_nonincreasing_times_rejected(self):
        for change in ('missing', 'time', 'identity'):
            doc, field = fixture()
            if change == 'missing': field['rows'][0]['depth_values'][0] = None
            elif change == 'time': field['rows'][1]['time'] = 0
            else: field['arm'] = 'other'
            with self.assertRaises(ValueError): build(doc, field, 'arm', 'body')

    def test_sampled_constant_front_needs_no_clipping(self):
        doc, field = fixture()
        for row in field['rows']: row['depth_values'] = [1, 1, 1]
        candidate = build(doc, field, 'arm', 'body')
        self.assertEqual([s['name'] for s in candidate['slots']], ['body', 'm4-tri-front-static'])
