import copy
import struct
import unittest
from autospine_workbench.targets.character43.occlusion_scope_order import inspect, timeline


class OcclusionOrderTests(unittest.TestCase):
    def test_timeline_keeps_float_boundaries_and_final_reset_separate(self):
        original=copy.deepcopy(self.doc)
        result=timeline(self.doc,'reach','sleeve','cape')
        start=struct.unpack('f',struct.pack('f',.1))[0]
        end=struct.unpack('f',struct.pack('f',.2))[0]
        self.assertEqual(result['intervals'],[
            dict(start=0.,end=start,reference_can_cover_in_order=True),
            dict(start=start,end=end,reference_can_cover_in_order=False)])
        self.assertEqual(result['endpoint'],dict(time=end,reference_can_cover_in_order=True))
        self.assertEqual(self.doc,original)

    def test_timeline_static_zero_duration_and_bounded_work(self):
        self.doc['animations']['reach']={}
        result=timeline(self.doc,'reach','sleeve','cape')
        self.assertEqual(result['intervals'],[])
        self.assertTrue(result['endpoint']['reference_can_cover_in_order'])
        self.doc['animations']['reach']={'drawOrder':[{}]*1025}
        self.assertEqual(timeline(self.doc,'reach','sleeve','cape')['status'],'unmeasured')

    def test_timeline_merges_equal_order_but_preserves_time_zero_key(self):
        self.doc['animations']['reach']={'drawOrder':[
            dict(time=0,offsets=[dict(slot='sleeve',offset=1)]),
            dict(time=1,offsets=[dict(slot='sleeve',offset=1)])],
            'bones':{'root':{'rotate':[dict(time=2,value=0)]}}}
        result=timeline(self.doc,'reach','sleeve','cape')
        self.assertEqual(result['intervals'],[dict(start=0.,end=2.,reference_can_cover_in_order=False)])

    def setUp(self):
        self.doc=dict(slots=[dict(name='sleeve'),dict(name='cape')],animations={'reach':{
            'drawOrder':[dict(time=.1,offsets=[dict(slot='sleeve',offset=1)]),
                         dict(time=.2,offsets=[])]}})

    def test_runtime_boundaries_reverse_seek_and_unchanged_source(self):
        original=copy.deepcopy(self.doc)
        start=struct.unpack('f',struct.pack('f',.1))[0]
        end=struct.unpack('f',struct.pack('f',.2))[0]
        for time,expected in [(end,True),(start,False),(.1,True),(0,True),(.15,False)]:
            result=inspect(self.doc,'reach',time,'sleeve','cape')
            self.assertEqual(result['reference_can_cover_in_order'],expected)
        self.assertEqual(self.doc,original)

    def test_static_and_invalid_identity(self):
        self.doc['animations']['reach']={}
        self.assertEqual(inspect(self.doc,'reach',1,'sleeve','cape')['status'],'reference_in_front')
        with self.assertRaises(ValueError):inspect(self.doc,'reach',0,'missing','cape')
        with self.assertRaises(ValueError):inspect(self.doc,'reach',float('nan'),'sleeve','cape')

    def test_colliding_float_times_not_silently_reordered(self):
        self.doc['animations']['reach']['drawOrder'][1]['time']=.10000000001
        with self.assertRaisesRegex(ValueError,'collision'):
            inspect(self.doc,'reach',0,'sleeve','cape')
