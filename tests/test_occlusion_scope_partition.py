from copy import deepcopy
import unittest
from test_depth_region_partition import source
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.occlusion_scope_partition import build


class ScopePartitionTests(unittest.TestCase):
    def fixture(self):
        doc,_=source();meshes=doc['skins'][0]['attachments']
        scope=dict(reference_slot='b',mesh_sha256=canonical_sha256(meshes['a']['a']),
                   reference_mesh_sha256=canonical_sha256(meshes['b']['b']),regions={'occlusion':[0]})
        return doc,scope

    def test_region_is_not_rebound_and_unknown_does_not_become_free(self):
        doc,scope=self.fixture();before=deepcopy(doc)
        candidate,report=build(doc,'a',scope)
        self.assertEqual([r['group'] for r in report['regions']],['occlusion','unclassified'])
        self.assertEqual(report['unclassified_triangles'],2)
        for time in [0,.25,.5,1]:
            expected=sample(doc,'test',time)[0];actual=sample(candidate,'test',time)[0]
            for row in report['regions']:self.assertEqual(actual[row['slot']],expected['a'])
        self.assertEqual(doc,before)
        self.assertFalse(report['solved_constraints'])
        self.assertFalse(report['motion_changed'])
        self.assertEqual(report['candidate_skeleton_sha256'],canonical_sha256(candidate))

    def test_other_roles_keep_their_meaning_and_no_constraint_is_solved(self):
        doc,scope=self.fixture();scope['regions'].update(fixed=[1],sliding=[2])
        _,report=build(doc,'a',scope)
        self.assertEqual([r['group'] for r in report['regions']],['occlusion','fixed','sliding'])
        self.assertFalse(report['solved_constraints'])

    def test_stale_reference_overlap_bad_roles_and_budget_rejected(self):
        for change in ('reference','source','overlap','bounds','boolean','unknown','empty','budget'):
            doc,scope=self.fixture()
            if change=='reference':scope['reference_mesh_sha256']='stale'
            elif change=='source':scope['mesh_sha256']='stale'
            elif change=='overlap':scope['regions']['free']=[0]
            elif change=='bounds':scope['regions']['occlusion']=[3]
            elif change=='boolean':scope['regions']['occlusion']=[True]
            elif change=='unknown':scope['regions']['invented']=[]
            elif change=='empty':scope['regions']['occlusion']=[]
            with self.subTest(change=change),self.assertRaises(ValueError):
                build(doc,'a',scope,part_limit=1 if change=='budget' else 128)


if __name__=='__main__':unittest.main()
