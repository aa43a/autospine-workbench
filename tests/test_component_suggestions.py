import unittest
from autospine_workbench.asset.planning.component_suggestions import build


class ComponentSuggestionTests(unittest.TestCase):
    def fixture(self, name='handwear-l'):
        layer = dict(layer_id='layer', name=name, semantic=None, bbox=[10,20,30,40])
        region = dict(id='component-0000', runs=[[y,0,20] for y in range(20)])
        entries = [(layer,b'',dict(components=[region],residual=dict(id='low-alpha-residual',runs=[])),'a'*64)]
        skeleton = {'bones':[dict(id=b,head_xy=[12,22],tail_xy=[25,35]) for b in ['upperarm_l','forearm_l','hand_l']]}
        bindings = {'bindings':[dict(layer_id='layer',options=[dict(bone_ids=['upperarm_l','forearm_l','hand_l'])])]}
        return entries, skeleton, bindings

    def test_unique_semantic_and_component_support_suggest_only(self):
        result = build(*self.fixture(), {})
        self.assertEqual(result['records'][0]['proposal']['side'],'left')
        self.assertEqual(result['records'][0]['status'],'suggested')
        self.assertEqual(result['records'][1]['status'],'blocked')
        self.assertFalse(result['production_authorized'])

    def test_ambiguous_semantics_opposite_side_and_no_coverage_stay_blocked(self):
        for name in ['objects','bottomwear','handwear-r']:
            self.assertEqual(build(*self.fixture(name), {})['records'][0]['status'],'blocked')
        entries, skeleton, bindings = self.fixture()
        entries[0][2]['components'][0]['runs'] = []
        self.assertEqual(build(entries,skeleton,bindings,{})['records'][0]['status'],'blocked')

    def test_conflicting_semantics_do_not_assign_arm_bones_to_leg(self):
        entries, skeleton, bindings = self.fixture(); entries[0][0]['semantic']='body.leg'
        self.assertEqual(build(entries,skeleton,bindings,{})['records'][0]['status'],'blocked')
