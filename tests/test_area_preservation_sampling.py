from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.projected_area_sampling import inspect


def fixture():
    return dict(bones=[dict(name='root',x=0,y=0,rotation=0)],
        animations={'move':{'bones':{'root':{'rotate':[dict(time=0,value=0),dict(time=1,value=0)]}}}},
        skins=[dict(attachments={'mesh':{'mesh':dict(triangles=[0,1,2],
            vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1])}})])


class PreservationSamplingTests(unittest.TestCase):
    def test_old_gate_passes_but_preservation_detects_key_and_midpoint_loss(self):
        source=fixture();result=deepcopy(source)
        result['animations']['move']['attachments']={'default':{'mesh':{'mesh':{'deform':[
            dict(time=0,vertices=[0,0,0,0,0,-.2]),dict(time=1,vertices=[0,0,0,0,0,-.2])]}}}}
        self.assertEqual(inspect(result,'move',['mesh'])['failures'],[])
        report=inspect(result,'move',['mesh'],preservation_source=source)
        self.assertEqual([r['time'] for r in report['failures']],[0,.5,1])
        self.assertEqual([r['at_key'] for r in report['failures']],[True,False,True])
        self.assertAlmostEqual(report['failures'][1]['preservation_failures'][0]['ratio'],.8)

    def test_changed_bone_motion_cannot_be_used_as_preservation_reference(self):
        source=fixture();result=deepcopy(source)
        result['animations']['move']['bones']['root']['rotate'][1]['value']=30
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            inspect(result,'move',['mesh'],preservation_source=source)

    def test_declared_repair_support_keeps_old_floor_only_for_incident_triangles(self):
        source=fixture();result=deepcopy(source)
        result['animations']['move']['attachments']={'default':{'mesh':{'mesh':{'deform':[
            dict(time=0,vertices=[0,0,0,0,0,-.2]),dict(time=1,vertices=[0,0,0,0,0,-.2])]}}}}
        self.assertTrue(inspect(result,'move',['mesh'],preservation_source=source,repair_support={'mesh':[]})['failures'])
        self.assertEqual(inspect(result,'move',['mesh'],preservation_source=source,repair_support={'mesh':[2]})['failures'],[])
        result['animations']['move']['attachments']['default']['mesh']['mesh']['deform'][1]['vertices'][-1]=-.6
        self.assertTrue(inspect(result,'move',['mesh'],preservation_source=source,repair_support={'mesh':[2]})['failures'])
