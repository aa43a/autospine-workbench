import unittest
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve import build
from autospine_workbench.targets.spine43.ordinary_sleeve import compile_region
from autospine_workbench.resolved_project import canonical_sha256


def inputs():
    source, draft, skeleton = fixture()
    skeleton['canvas'] = [64, 64]
    for i, bone in enumerate(skeleton['bones']):
        bone['length'] = 10.
        bone['setup_local'] = dict(x=10. if i else 0., y=0., rotation_degrees=0.)
    skeleton['bones'][0]['parent_id'] = None
    source['skeleton_sha256'] = canonical_sha256(skeleton)
    mesh = source['records'][0]['mesh']
    mesh['uvs'] = [[x/64, y/64] for x, y in mesh['vertices_xy']]
    report = build(source, draft, skeleton)
    return report, report['records'][0], mesh, skeleton


class OrdinarySleeveTargetTests(unittest.TestCase):
    def test_original_bones_four_animations_and_target_interpolation(self):
        doc, qa = compile_region(*inputs())
        self.assertEqual(len(doc['bones']), 3)
        self.assertEqual(set(doc['animations']), {'forearm', 'hand', 'combined_same', 'combined_opposed'})
        self.assertTrue(qa['passed'])
        self.assertTrue(all(check['sample_count'] == 257 for check in qa['checks'].values()))
        self.assertTrue(all(check['key_error_px'] < 1e-7 for check in qa['checks'].values()))
        self.assertTrue(all('attachments' not in animation for animation in doc['animations'].values()))
        self.assertEqual(qa['runtime_status'], 'not_evaluated')

    def test_missing_tracks_and_unknown_ownership_cannot_be_exported(self):
        args = inputs(); args[1]['tracks'].pop()
        with self.assertRaises(ValueError): compile_region(*args)
        args = inputs(); args[1]['status'] = 'blocked'; args[1]['reason_codes'] = ['ownership_review_required']
        with self.assertRaises(ValueError): compile_region(*args)
