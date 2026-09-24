from unittest.mock import patch
from test_motion_repair_draft import RepairDraftTests
from test_region_order_bundle import fixture
from autospine_workbench.automation.motion_partition_draft import meshes
from autospine_workbench.automation import motion_repair_draft as draft


class RegionOrderDraftTests(RepairDraftTests):
    def setUp(self):
        super().setUp()
        self.files, _ = fixture()
        self.report['rows'][0]['slot'] = 'a'
        self.mesh = meshes(self.files, 'a'*64)['rows'][0]
        p = patch('autospine_workbench.automation.motion_target_jobs.context',
                  return_value=({'artifact_sha256':'a'*64}, self.files))
        p.start(); self.addCleanup(p.stop)

    def body(self, **changes):
        value = super().body(**changes); value['slot'] = 'a'; return value

    def ordered(self):
        value = self.body(); value['action'] = 'region_order'
        value['region_order'] = dict(mesh_sha256=self.mesh['mesh_sha256'],
                                     triangles=[2,0], reference_slot='b', side='after')
        return value

    def test_order_selection_roundtrip_and_withdrawal(self):
        saved = draft.save(self.manager, 'job', self.ordered())
        self.assertEqual(saved['history'][0]['region_order']['triangles'], [0,2])
        self.assertEqual(draft.inspect(self.manager,'job'), saved)
        body = self.body(); body['action'] = 'withdraw'
        result = draft.save(self.manager,'job',body)
        self.assertEqual(result['history'][0], saved['history'][0])
        self.assertEqual(result['history'][1]['action'], 'withdraw')

    def test_bad_order_selection_cannot_enter_history(self):
        for field, value in [('mesh_sha256','0'*64), ('triangles',[True]),
                             ('reference_slot','a'), ('reference_slot','missing'), ('side','front')]:
            body = self.ordered(); body['region_order'][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                draft.save(self.manager,'job',body)
        body = self.ordered(); del body['region_order']
        with self.assertRaisesRegex(RuntimeError,'region_order_required'):
            draft.save(self.manager,'job',body)
        self.assertEqual(draft.inspect(self.manager,'job')['history'], [])
