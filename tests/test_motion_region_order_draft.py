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

    def test_interval_roundtrip_and_invalid_duration(self):
        import json
        document = json.loads(self.files['skeleton.json'])
        document['animations']['reach'] = document['animations'].pop('test')
        self.files['skeleton.json'] = json.dumps(document).encode()
        body = self.ordered(); body['region_order']['interval'] = [.25, .75]
        saved = draft.save(self.manager, 'job', body)
        self.assertEqual(saved['history'][0]['region_order']['interval'], [.25, .75])
        self.assertEqual(draft.inspect(self.manager, 'job'), saved)
        body['expected_revision'] = saved['revision']
        for interval in (None, [0, 2], [.5, .5], [False, .5]):
            body['region_order']['interval'] = interval
            with self.assertRaisesRegex(RuntimeError, 'region_order_unsupported'):
                draft.save(self.manager, 'job', body)
        self.assertEqual(draft.inspect(self.manager, 'job'), saved)
