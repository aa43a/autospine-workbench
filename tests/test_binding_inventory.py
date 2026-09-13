from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.binding_inventory import inspect


class BindingInventoryTests(unittest.TestCase):
    def setUp(self):
        self.doc=dict(bones=[dict(name='forearm_l'),dict(name='hand_l')],skins=[dict(attachments={'part':{'part':dict(
            type='mesh',uvs=[0,0,1,1],vertices=[2,0,1,2,.75,1,1,2,.25,1,1,3,4,1.])}})])
        self.layers=[dict(layer_id='arm',regions=[dict(region_id='part',state='weighted_candidate')])]

    def test_actual_weights_do_not_imply_semantic_approval(self):
        report=inspect(self.doc,self.layers);row=report['regions'][0]
        self.assertEqual(report['semantic_review'],'not_inferred');self.assertEqual(row['vertex_count'],2)
        self.assertEqual(row['max_influences'],2);self.assertEqual(row['influences'][0]['bone'],'forearm_l')
        self.assertEqual(row['influences'][1]['mean_weight'],.625)

    def test_nonfinite_bad_indices_truncation_and_non_normalized_weights_fail(self):
        for data in [[1,2,0,0,1],[1,0,0,0,float('nan')],[2,0,0,0,1],[1,0,0,0,.5],
                     [2,0,0,0,.5,0,0,0,.5],[True,0,0,0,1]]:
            doc=deepcopy(self.doc);doc['skins'][0]['attachments']['part']['part']['vertices']=data
            with self.subTest(data=data),self.assertRaises(ValueError):inspect(doc,self.layers)

    def test_unweighted_regions_are_not_presented_for_approval(self):
        self.layers[0]['regions'][0]['state']='static_reference'
        self.assertEqual(inspect(self.doc,self.layers)['regions'],[])

    def test_zero_weight_entries_are_not_reported_as_drivers(self):
        attachment=self.doc['skins'][0]['attachments']['part']['part']
        attachment['vertices']=[2,0,0,0,0.,1,0,0,1.,1,1,0,0,1.]
        row=inspect(self.doc,self.layers)['regions'][0]
        self.assertEqual([b['bone'] for b in row['influences']],['hand_l'])
        self.assertEqual(row['max_influences'],1)
