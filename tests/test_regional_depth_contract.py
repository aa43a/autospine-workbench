from copy import deepcopy
import unittest
from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.regional_depth_contract import verify


class RegionalContractTests(unittest.TestCase):
    def fixture(self):
        doc, _ = source(); candidate, _ = build(doc, ['a'])
        slots = [s['name'] for s in candidate['slots']]; names = slots[::-1]
        candidate['animations']['test']['drawOrder'] = [dict(time=.5, offsets=[
            dict(slot=s, offset=names.index(s)-i) for i, s in enumerate(slots)])]
        return doc, candidate, dict(status='candidate', failures=[], frames=[dict(time=.5, order=names)])

    def test_exact_transform_and_source_identity(self):
        doc, candidate, order = self.fixture(); original = deepcopy(doc)
        report = verify(doc, candidate, 'test', ['a'], order)
        self.assertEqual(report['order_keys'], 1)
        self.assertEqual(doc, original)
        self.assertNotEqual(report['source_skeleton_sha256'], report['candidate_skeleton_sha256'])

    def test_rejects_unreported_rig_mesh_and_animation_changes(self):
        for kind in ['bone', 'weight', 'uv', 'triangle', 'animation']:
            with self.subTest(kind=kind):
                doc, candidate, order = self.fixture()
                mesh = candidate['skins'][0]['attachments']['a-depth-001']['a-depth-001']
                if kind == 'bone': candidate['bones'][0]['x'] = 10
                elif kind == 'weight': mesh['vertices'][-1] = .9
                elif kind == 'uv': mesh['uvs'][0] = .9
                elif kind == 'triangle': mesh['triangles'] = []
                else: candidate['animations']['test']['bones']['cloth']['rotate'][1]['value'] = 40
                with self.assertRaisesRegex(ValueError, 'unexpected_edit'):
                    verify(doc, candidate, 'test', ['a'], order)

    def test_invalid_or_incomplete_order_rejected(self):
        for kind in ['failed', 'duplicate', 'time', 'slots']:
            doc, candidate, order = self.fixture()
            if kind == 'failed': order['failures'] = [{'reason_code': 'unknown'}]
            elif kind == 'duplicate': order['frames'] *= 2
            elif kind == 'time': order['frames'][0]['time'] = float('nan')
            else: order['frames'][0]['order'][0] = 'missing'
            with self.assertRaises(ValueError): verify(doc, candidate, 'test', ['a'], order)
