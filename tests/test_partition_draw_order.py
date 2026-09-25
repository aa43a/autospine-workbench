from copy import deepcopy
import unittest
from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.spine42_draw_order_offsets import apply_spine42_draw_order_offsets as decode


class PartitionDrawOrderTests(unittest.TestCase):
    def test_existing_order_reset_and_all_deform_samples_preserved(self):
        doc,_=source()
        keys=[dict(time=.1,offsets=[dict(slot='a',offset=1)]),dict(time=.7)]
        doc['animations']['test']['drawOrder']=keys
        doc['animations']['other']=dict(drawOrder=[dict(offsets=[])])
        original=deepcopy(doc)
        result,report=build(doc,['a'],preserve_draw_order=True,
                            triangle_labels={'a':['covered','free','covered']})
        parts=[r['slot'] for r in report['regions']]
        names=[s['name'] for s in result['slots']]
        tracks=result['animations']['test']['drawOrder']
        self.assertEqual([k['time'] for k in tracks],[.1,.7])
        self.assertEqual(list(decode(names,tracks[0]['offsets'])),['b',*parts])
        self.assertEqual(list(decode(names,tracks[1]['offsets'])),names)
        self.assertNotIn('time',result['animations']['other']['drawOrder'][0])
        for time in (0,.099,.1,.35,.7,1):
            expected=sample(doc,'test',time)[0]
            actual=sample(result,'test',time)[0]
            for part in parts:self.assertEqual(actual[part],expected['a'])
            self.assertEqual(actual['b'],expected['b'])
        self.assertEqual(doc,original)
        self.assertEqual(report['source_draw_order']['key_count'],3)

    def test_invalid_or_colliding_keys_fail_without_mutating_source(self):
        for keys in ([dict(time=.1),dict(time=.10000000001)],
                     [dict(time=-1)], [dict(time=0,curve='stepped')],
                     [dict(time=0,offsets=[dict(slot='missing',offset=1)])]):
            doc,_=source();doc['animations']['test']['drawOrder']=keys
            original=deepcopy(doc)
            with self.assertRaises(ValueError):build(doc,['a'],preserve_draw_order=True)
            self.assertEqual(doc,original)
        doc,_=source();doc['animations']['test']['draworder']=[]
        with self.assertRaisesRegex(ValueError,'legacy'):
            build(doc,['a'],preserve_draw_order=True)


if __name__=='__main__':unittest.main()
