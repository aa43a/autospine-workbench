from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.motion_area_repair import repair
from autospine_workbench.targets.spine43.continuous_pose import world,area


class MotionRepairTests(unittest.TestCase):
    def fixture(self):
        vertices=[]
        for x,y in [(10,0),(11,0),(10,1)]:vertices.extend([2,0,x,y,.5,1,x-10,y,.5])
        vertices.extend([1,0,8,0,1])
        return dict(bones=[dict(name='root',x=0,y=0,rotation=0),dict(name='child',parent='root',x=10,y=0,rotation=0)],
          skins=[{'attachments':{'a':{'a':dict(vertices=vertices,triangles=[0,1,2])}}}],
          animations={'move':{'bones':{'child':{'rotate':[dict(time=0,value=0),dict(time=1,value=120),dict(time=2,value=0)]}}}})

    def test_repairs_blend_compression_without_changing_weights_or_fixed_vertices(self):
        original=self.fixture();saved=deepcopy(original);result,report=repair(original,['a'])
        self.assertEqual(original,saved);self.assertEqual(result['skins'],original['skins']);self.assertEqual(result['bones'],original['bones'])
        setup=world(original,0)['a'];initial=area(setup,[0,1,2])
        self.assertLess(area(world(original,1)['a'],[0,1,2])/initial,.5)
        for i in range(257):
            corrected=world(result,i/128)['a'];baseline=world(original,i/128)['a']
            self.assertGreaterEqual(area(corrected,[0,1,2])/initial,.5)
            self.assertEqual(corrected[3],baseline[3])
        self.assertEqual(world(result,0),world(original,0));self.assertEqual(world(result,2),world(original,2))
        self.assertLessEqual(report['records'][0]['max_displacement_px'],report['records'][0]['budget_px'])

    def test_existing_deform_cannot_be_overwritten(self):
        doc=self.fixture();doc['animations']['move']['attachments']={'default':{'a':{}}}
        with self.assertRaisesRegex(ValueError,'existing_deform'):repair(doc,['a'])
