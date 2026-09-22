from copy import deepcopy
import unittest
from m4_clip_candidate import build,validate_segments


def fixture():
    mesh=dict(type='mesh',uvs=[0,0,1,0,0,1],triangles=[0,1,2],vertices=[0,0,2,0,0,2])
    doc=dict(bones=[dict(name='root')],slots=[dict(name=n,bone='root',attachment=n) for n in ('arm','body')],
             skins=[dict(name='default',attachments={n:{n:deepcopy(mesh)} for n in ('arm','body')})],
             animations={'external-motion':dict(bones={'root':{'rotate':[dict(time=0,value=0),dict(time=1,value=30)]}},
                 attachments={'default':{'arm':{'arm':{'deform':[dict(time=0,vertices=[0]*6),dict(time=1,vertices=[1]*6)]}}}})})
    segment=dict(start=0,end=1,frames=[dict(time=t,points=[[t,0],[2+t,0],[t,2]]) for t in (0,1)])
    return doc,dict(segments=[segment])


class ClipCandidateTests(unittest.TestCase):
    def test_preserves_original_and_duplicates_deformation(self):
        doc,report=fixture();original=deepcopy(doc);result=build(doc,report,'arm','body')
        self.assertEqual(doc,original)
        self.assertEqual(result['animations']['external-motion']['bones'],doc['animations']['external-motion']['bones'])
        attachments=result['skins'][0]['attachments']
        self.assertEqual(attachments['arm'],doc['skins'][0]['attachments']['arm'])
        tracks=result['animations']['external-motion']['attachments']['default']
        self.assertEqual(tracks['m4-front-mesh']['m4-front-mesh'],tracks['arm']['arm'])
        self.assertEqual(attachments['m4-clip-back']['clip-000']['end'],'arm')
        self.assertTrue(attachments['m4-clip-back']['clip-000']['inverse'])
        self.assertFalse(attachments['m4-clip-front']['clip-000']['inverse'])
        self.assertEqual(tracks['m4-clip-front']['clip-000']['deform'][1]['vertices'],[1,0,1,0,1,0])

    def test_bad_frame_dimensions_and_nan_rejected(self):
        for replacement in ([[0,0]],[[0,0],[2,0],[float('nan'),2]]):
            _,report=fixture();report['segments'][0]['frames'][1]['points']=replacement
            with self.assertRaisesRegex(ValueError,'frame_points'):validate_segments(report['segments'])

    def test_gap_and_duplicate_times_rejected(self):
        _,report=fixture();segment=deepcopy(report['segments'][0]);segment['start']=1.1
        with self.assertRaisesRegex(ValueError,'segment_time'):validate_segments(report['segments']+[segment])
        _,report=fixture();report['segments'][0]['frames'].insert(1,report['segments'][0]['frames'][0])
        with self.assertRaisesRegex(ValueError,'frame_time'):validate_segments(report['segments'])

    def test_order_and_collision_rejected(self):
        doc,report=fixture();doc['slots'].reverse()
        with self.assertRaisesRegex(ValueError,'order_unsupported'):build(doc,report,'arm','body')
        doc,report=fixture();doc['bones'].append(dict(name='m4-clip-world'))
        with self.assertRaisesRegex(ValueError,'collision'):build(doc,report,'arm','body')

    def test_empty_segments_rejected(self):
        with self.assertRaisesRegex(ValueError,'segment_budget'):validate_segments([])
