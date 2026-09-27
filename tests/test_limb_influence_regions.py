from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.limb_influence_regions import classify


def source():
    doc = dict(bones=[dict(name=n) for n in ('upperarm_r','forearm_r','hand_r','chest')])
    mesh = dict(type='mesh', vertices=[1,0,0,0,1, 1,1,1,0,1, 1,2,0,1,1],
                uvs=[0,0,1,0,0,1], triangles=[0,0,0,1,1,1,2,2,2,0,1,2])
    return doc,mesh


class LimbInfluenceRegionsTests(unittest.TestCase):
    def test_complete_sets_preserved_without_mutation(self):
        doc,mesh=source();before=deepcopy((doc,mesh))
        labels,report=classify(doc,mesh,'r')
        self.assertEqual(labels,['upperarm','forearm','hand','transition:forearm,hand,upperarm'])
        self.assertFalse(report['selected']);self.assertEqual((doc,mesh),before)

    def test_tiny_influence_is_not_discarded(self):
        doc,mesh=source()
        mesh['vertices'][:5]=[2,0,0,0,.999999,3,0,0,.000001]
        labels,_=classify(doc,mesh,'r')
        self.assertEqual(labels[0],'unmapped');self.assertEqual(labels[-1],'unmapped')

    def test_invalid_weights_and_indices_fail(self):
        for field,index,value in [('vertices',4,-1),('vertices',1,99),('triangles',0,20)]:
            doc,mesh=source();mesh[field][index]=value
            with self.assertRaises(ValueError):classify(doc,mesh,'r')
