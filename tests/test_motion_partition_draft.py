import copy
from unittest.mock import patch
from test_motion_repair_draft import RepairDraftTests
from autospine_workbench.automation.motion_partition_draft import meshes
from autospine_workbench.automation import motion_repair_draft as draft
from test_repair_feasibility import evidence


class PartitionTests(RepairDraftTests):
    def setUp(self):
        super().setUp();self.files=evidence()
        self.report['rows'][0]['slot']='mesh'
        self.mesh=meshes(self.files,'a'*64)['rows'][0]
        p=patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'a'*64},self.files))
        p.start();self.addCleanup(p.stop)

    def body(self,**changes):
        value=super().body(**changes);value['slot']='mesh';return value

    def test_region_persists_and_withdraw_keeps_history(self):
        body=self.body();body['partition']=dict(mesh_sha256=self.mesh['mesh_sha256'],triangles=[0],bone='a')
        result=draft.save(self.manager,'job',body)
        self.assertEqual(result['history'][-1]['partition']['triangles'],[0])
        self.assertFalse(result['repair_executed'])
        withdrawal=self.body();withdrawal['action']='withdraw'
        result=draft.save(self.manager,'job',withdrawal)
        self.assertEqual(result['history'][0]['partition']['bone'],'a')

    def test_stale_mesh_out_of_range_and_unknown_bone_rejected(self):
        original=dict(mesh_sha256=self.mesh['mesh_sha256'],triangles=[0],bone='a')
        for key,value in [('mesh_sha256','b'*64),('triangles',[99]),('triangles',[0,0]),('triangles',[True]),('bone','missing')]:
            body=self.body();body['partition']={**copy.deepcopy(original),key:value}
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):draft.save(self.manager,'job',body)
