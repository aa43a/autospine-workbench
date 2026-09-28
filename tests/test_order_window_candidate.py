from copy import deepcopy
import unittest
from m4_order_window_candidate import compile_window


class OrderWindowTests(unittest.TestCase):
    def test_only_two_order_keys_change_and_restore_setup(self):
        doc=dict(slots=[dict(name=n) for n in ['hand','inner','leg','front']],
                 animations={'external-motion':dict(bones={'root':{'rotate':[dict(time=0,value=12)]}})})
        original=deepcopy(doc); result=compile_window(doc,'hand','leg',.45,.6166665)
        self.assertEqual(doc,original)
        self.assertEqual(result['animations']['external-motion']['drawOrder'],[
            dict(time=.45,offsets=[dict(slot='hand',offset=2),dict(slot='inner',offset=-1),dict(slot='leg',offset=-1),dict(slot='front',offset=0)]),
            dict(time=.6166665,offsets=[])])
        del result['animations']['external-motion']['drawOrder'];self.assertEqual(result,doc)

    def test_existing_decisions_and_invalid_windows_rejected(self):
        doc=dict(slots=[dict(name='hand'),dict(name='leg')],animations={'external-motion':{'drawOrder':[dict(time=0,offsets=[])]}})
        with self.assertRaisesRegex(ValueError,'existing'):compile_window(doc,'hand','leg',0,1)
        doc['animations']['external-motion'].clear()
        with self.assertRaisesRegex(ValueError,'times'):compile_window(doc,'hand','leg',1,0)
        with self.assertRaisesRegex(ValueError,'slots'):compile_window(doc,'hand','missing',0,1)
