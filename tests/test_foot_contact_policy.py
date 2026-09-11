"""Shoe support cannot be supplied by the wrong leg or lower-only overlap."""
import unittest
from autospine_workbench.automation.foot_contact_policy import contact_evidence,propose
from autospine_workbench.automation.head_binding_policy import propose as previous
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_head_binding_policy import source


class FootContactPolicyTests(unittest.TestCase):
    def setUp(self):
        self.shoe={(x,y) for x in range(10) for y in range(10)}
        self.own={(x,y) for x in range(8) for y in range(10)}
        self.other={(x+100,y) for x,y in self.own}

    def test_distinct_same_side_and_cuff_support(self):
        values,checks=contact_evidence(self.shoe,self.own,self.other,[0,0,10,10],'l')
        self.assertTrue(all(checks.values()));self.assertEqual(values['same_side_overlap_ratio'],.8)
        self.assertEqual(values['cuff_overlap_ratio'],.8)

    def test_wrong_side_and_ambiguous_sides_rejected(self):
        for left,right in ((self.other,self.own),(self.own,self.own)):
            _,checks=contact_evidence(self.shoe,left,right,[0,0,10,10],'l')
            self.assertFalse(checks['reviewed_leg_side_margin'])

    def test_lower_overlap_does_not_prove_cuff_connection(self):
        lower={(x,y) for x,y in self.shoe if y>=2}
        _,checks=contact_evidence(self.shoe,lower,self.other,[0,0,10,10],'l')
        self.assertTrue(checks['reviewed_leg_overlap']);self.assertFalse(checks['reviewed_leg_cuff_overlap'])

    def test_translation_invariance_and_empty_rejection(self):
        shift=lambda pts:{(x+20,y+40) for x,y in pts}
        self.assertEqual(contact_evidence(self.shoe,self.own,self.other,[0,0,10,10],'l'),
            contact_evidence(shift(self.shoe),shift(self.own),shift(self.other),[20,40,30,50],'l'))
        self.assertFalse(any(contact_evidence(set(),self.own,self.other,[0,0,10,10],'l')[1].values()))

    def test_previous_policy_is_not_modified(self):
        s=source();before=canonical_sha256(previous(s));doc=propose(s)
        self.assertEqual(doc['rows'],previous(s)['rows']);self.assertEqual(before,canonical_sha256(previous(s)))
