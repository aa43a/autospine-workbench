import unittest
from autospine_workbench.targets.character43.depth_interval_evidence import requests,IntervalEvidenceError


class Probe:
    def __init__(self,visible):self.visible=visible
    def pair(self,a,b,t):return dict(overlap_pixels=int(t in self.visible)*10)


class IntervalTests(unittest.TestCase):
    def row(self):
        return dict(tick=0,ambiguous=False,support='no_overlap',current_front_slot='body',
                    interval_sample=dict(tick=500000,ambiguous=False,support='sampled',current_front_slot='arm'))

    def test_new_overlap_uses_its_own_depth(self):
        pair=dict(arm_slot='arm',torso_slot='body')
        actual=requests(pair,self.row(),[0,.5],Probe({.5}),strict=True)
        self.assertEqual(actual,[('body','arm',dict(time=.5,overlap_pixels=10))])
        self.assertEqual(requests(pair,self.row(),[0,.5],Probe({.5}))[0][:2],('arm','body'))

    def test_visible_reversal_needs_an_additional_switch(self):
        row=self.row();row['support']='sampled'
        row['evidence_states']={'A':1};row['interval_sample']['evidence_states']={'B':1}
        with self.assertRaisesRegex(IntervalEvidenceError,'changes_within_interval') as context:
            requests(dict(arm_slot='arm',torso_slot='body'),row,[0,.5],Probe({0,.5}),strict=True)
        self.assertEqual(len(context.exception.details['samples']),2)
        self.assertEqual([s['evidence_states'] for s in context.exception.details['samples']],[{'A':1},{'B':1}])

    def test_missing_or_stale_midpoint_cannot_borrow_origin(self):
        for tick in (None,400000,float('nan')):
            row=self.row()
            if tick is None:row.pop('interval_sample')
            else:row['interval_sample']['tick']=tick
            with self.assertRaisesRegex(IntervalEvidenceError,'depth_missing'):
                requests(dict(arm_slot='arm',torso_slot='body'),row,[0,.5],Probe({.5}),strict=True)

    def test_unknown_and_unobserved_visible_support_do_not_pass(self):
        for change in ({'ambiguous':True},{'support':'no_overlap'}):
            row=self.row();row['interval_sample'].update(change)
            with self.assertRaisesRegex(IntervalEvidenceError,'depth_straddle'):
                requests(dict(arm_slot='arm',torso_slot='body'),row,[0,.5],Probe({.5}),strict=True)
