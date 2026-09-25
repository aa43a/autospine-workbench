import copy
import struct
import unittest
from autospine_workbench.targets.character43.occlusion_scope_order import inspect


class OcclusionOrderTests(unittest.TestCase):
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
