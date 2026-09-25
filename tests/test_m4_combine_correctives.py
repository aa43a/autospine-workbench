from copy import deepcopy
import unittest
from m4_combine_correctives import merge


class MergeCorrectivesTests(unittest.TestCase):
    def test_disjoint_tracks_combine_without_mutating_parent(self):
        parent={'animations':{'external-motion':{'bones':{'root':{}},'attachments':{'default':{'a':{},'b':{}}}}}}
        a=deepcopy(parent);a['animations']['external-motion']['attachments']['default']['a']={'new':1}
        b=deepcopy(parent);b['animations']['external-motion']['attachments']['default']['b']={'new':2}
        result,slots=merge(parent,[(a,['a']),(b,['b'])])
        self.assertEqual(slots,['a','b'])
        self.assertEqual(result['animations']['external-motion']['attachments']['default'],{'a':{'new':1},'b':{'new':2}})
        self.assertEqual(parent['animations']['external-motion']['attachments']['default']['a'],{})
        with self.assertRaises(ValueError):merge(parent,[(a,['a']),(a,['a'])])
        b['animations']['external-motion']['bones']['root']={'rotate':[1]}
        with self.assertRaises(ValueError):merge(parent,[(b,['b'])])


if __name__=='__main__':unittest.main()
