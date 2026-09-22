from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.pose_material_overlay import activation,build


class PoseMaterialTests(unittest.TestCase):
    def fixture(self):
        mesh=dict(type='mesh',uvs=[0,0,1,0,0,1],triangles=[0,1,2],vertices=[1,0,0,0,1]*3)
        doc=dict(bones=[dict(name='thigh',rotation=0,x=0,y=0),dict(name='calf',parent='thigh',rotation=0,x=1,y=0)],
                 slots=[dict(name='leg',bone='thigh',attachment='leg')],
                 skins=[dict(name='default',attachments={'leg':{'leg':mesh}})],
                 animations={'move':{'bones':{'calf':{'rotate':[dict(time=0,value=0),dict(time=1,value=90)]}}}})
        variant=deepcopy(doc);variant['skins'][0]['attachments']['leg']['leg']['uvs'][0]=.1
        return doc,variant

    def test_original_preserved_and_overlay_disabled_at_start(self):
        doc,variant=self.fixture();before=deepcopy(doc)
        out,report=build(doc,variant,[dict(slot='leg',joint='calf')],[0,.5,1],animation='move')
        self.assertEqual(doc,before)
        self.assertEqual(out['skins'][0]['attachments']['leg'],doc['skins'][0]['attachments']['leg'])
        self.assertEqual(out['animations']['move']['bones'],doc['animations']['move']['bones'])
        self.assertEqual(out['slots'][1]['color'],'ffffff00')
        keys=report['records'][0]['alpha_keys']
        self.assertEqual(keys[0]['value'],0);self.assertEqual(keys[-1]['value'],1)
        self.assertGreater(keys[1]['value'],0);self.assertLess(keys[1]['value'],1)

    def test_draw_order_and_non_uv_mutation_rejected(self):
        doc,variant=self.fixture();doc['animations']['move']['drawOrder']=[{}]
        variant['animations']=deepcopy(doc['animations'])
        with self.assertRaisesRegex(ValueError,'draw_order'):build(doc,variant,[],[0],animation='move')
        doc,variant=self.fixture();variant['skins'][0]['attachments']['leg']['leg']['vertices'][2]=1
        with self.assertRaisesRegex(ValueError,'non_uv'):build(doc,variant,[dict(slot='leg',joint='calf')],[0],animation='move')

    def test_activation_is_symmetric_and_rejects_nonfinite(self):
        self.assertEqual(activation(-50),activation(50));self.assertEqual(activation(20),0)
        with self.assertRaisesRegex(ValueError,'activation'):activation(float('nan'))
