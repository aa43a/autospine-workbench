from copy import deepcopy
import unittest
from test_torso_projection import fixture
from autospine_workbench.targets.character43.torso_projection_validation import contact_preservation


class TorsoValidationTests(unittest.TestCase):
    def setUp(self):
        self.original=fixture()
        self.original['bones'][0]['name']='foot_l'
        self.original['bones'][1]['parent']='foot_l'
        self.original['animations']['move']['bones']={}

    def test_unchanged_paths_do_not_claim_floor_contact(self):
        report=contact_preservation(self.original,deepcopy(self.original),'move',[0,.5,1])
        self.assertEqual(report['status'],'sampled_paths_preserved')
        self.assertEqual(report['records'][0]['vertex_count'],3)
        self.assertIn('not_floor_or_sole_contact',report['scope'])

    def test_deform_can_move_foot_without_changing_bone_animation(self):
        candidate=deepcopy(self.original)
        candidate['animations']['move']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0]*6),dict(time=1,vertices=[1,0]*3)]}}}}
        report=contact_preservation(self.original,candidate,'move',[0,.5,1])
        self.assertEqual(report['status'],'foot_surface_changed')
        self.assertEqual(report['records'][0]['maximum_displacement_px'],1)
        self.assertTrue(report['bone_animation_unchanged'])

    def test_bone_mutation_and_missing_feet_cannot_pass(self):
        candidate=deepcopy(self.original);candidate['bones'][0]['x']=99
        with self.assertRaisesRegex(ValueError,'rig_changed'):
            contact_preservation(self.original,candidate,'move',[0,1])
        report=contact_preservation(fixture(),fixture(),'move',[0,1])
        self.assertEqual(report['status'],'foot_surface_unmeasured')


if __name__=='__main__':unittest.main()
