from copy import deepcopy
from types import SimpleNamespace
import unittest
from autospine_workbench.automation.binding_review_focus import explain


class BindingReviewFocusTests(unittest.TestCase):
    def fixture(self):
        source=SimpleNamespace(candidate={'layers':[{'layer_id':'face','semantic':'body.face'}]},
            draft={'records':[{'layer_id':'face','action':'pending','option_id':None}]},
            bindings={'bindings':[{'layer_id':'eye','reason_codes':['head_detail_name_candidate','visual_parent_review_required'],
                                  'options':[{'id':'rigid:head'}]}]})
        proposal={'rows':[{'layer_id':'eye','status':'needs_review','reason_codes':['policy_capability_unsupported']},
            {'layer_id':'face','status':'needs_review','reason_codes':['face_above_neck'],'evidence':{'neck_layer_id':'neck'}},
            {'layer_id':'neck','status':'needs_review'}]}
        return source,proposal

    def test_one_prerequisite_group_without_modifying_policy(self):
        source,proposal=self.fixture(); before=deepcopy(proposal)
        group=explain(source,proposal)[0]
        self.assertEqual(group['prerequisite_layer_ids'],['face','neck'])
        self.assertEqual(group['dependent_layer_ids'],['eye'])
        self.assertFalse(group['automatic_adoption_guaranteed'])
        self.assertEqual(proposal,before)

    def test_explicit_decisions_and_ambiguous_faces_preserved(self):
        for action in ['bind','exclude']:
            source,proposal=self.fixture();source.draft['records'][0]['action']=action
            self.assertEqual(explain(source,proposal),[])
        source,proposal=self.fixture();source.candidate['layers']*=2
        self.assertEqual(explain(source,proposal),[])

    def test_real_geometry_failures_are_not_hidden_as_dependencies(self):
        source,proposal=self.fixture();proposal['rows'][0]['reason_codes']=['visible_face_containment']
        self.assertEqual(explain(source,proposal),[])
        source,proposal=self.fixture();source.bindings['bindings'][0]['options'].append({'id':'rigid:chest'})
        self.assertEqual(explain(source,proposal),[])
