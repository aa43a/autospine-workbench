from copy import deepcopy
import unittest
from autospine_workbench.automation.character_cohort import summarize


class CohortTests(unittest.TestCase):
    def fixture(self):
        cohort=dict(schema='autospine.character-milestone-cohort/v1',authority='none',purpose='development_integration_not_independent_holdout',
                    cohort_id='fixed',required_animations=['idle','wave-left','walk'],characters=[dict(project_id=p,name=p,structure=s,original_split='visible') for p,s in zip(['a','b','c'],['ordinary_limbs','ordinary_sleeve_repair','wide_sleeve_repair'])])
        return cohort,{p:{} for p in ['a','b','c']}

    def complete(self):
        return dict(job=dict(status='needs_review',animations=['idle','wave-left','walk'],runtime={'geometry_status':'passed'},
                             layers=[dict(layer_id='arm',state='weighted_candidate',binding_decision={'decision_source':'explicit_selection','action':'bind','option_id':'mesh_chain:l:arm'})]),
                    verified_runtime={'passed':True,'results':[dict(animation=a,index=i,time=i/30)
                        for a in ['idle','wave-left','walk'] for i in range(3)]},
                    visual_review={'aspects':{k:'acceptable' for k in ['setup','draw_order','connections','motion']}})

    def test_missing_characters_stay_in_denominator_and_unknown_is_not_failure_rate_zero(self):
        c,o=self.fixture();r=summarize(c,o)
        self.assertEqual(r['metrics']['completion_rate'],0);self.assertIsNone(r['metrics']['runtime_failure_rate'])
        o['a']=self.complete();r=summarize(c,o)
        self.assertEqual(r['metrics']['completion_rate'],1/3)
        self.assertEqual(r['metrics']['runtime_measured_characters'],1)
        self.assertIsNone(r['metrics']['incorrect_auto_adoption_rate'])

    def test_static_pending_and_unreviewed_never_count_as_complete(self):
        c,o=self.fixture();o['a']=self.complete();o['b']=self.complete();o['c']=self.complete()
        o['a']['job']['layers'][0]['state']='static_reference'
        o['b']['job']['layers'][0]['binding_decision']['decision_source']='pending'
        o['c']['visual_review']['aspects']['connections']='not_reviewed'
        self.assertEqual(summarize(c,o)['metrics']['completed_characters'],0)

    def test_diagnostic_motion_is_not_walk_and_inventory_is_fixed(self):
        c,o=self.fixture();o['a']=self.complete();o['a']['job']['animations']=['limb-flex-15']
        self.assertEqual(summarize(c,o)['characters'][0]['missing_animations'],['idle','walk','wave-left'])
        o.pop('b')
        with self.assertRaisesRegex(ValueError,'inventory'):summarize(c,o)

    def test_visual_stopwatch_does_not_become_total_human_labor(self):
        c,o=self.fixture();o['a']=self.complete()
        o['a']['visual_review']['timing']=dict(method='operator_stopwatch_v1',scope='whole_character_visual_review_session',seconds=90)
        result=summarize(c,o)
        self.assertEqual(result['characters'][0]['visual_review_session_minutes'],1.5)
        self.assertIsNone(result['characters'][1]['visual_review_session_minutes'])
        self.assertIsNone(result['metrics']['human_review_minutes'])

    def test_automatic_binding_requires_current_evidence_even_with_green_runtime(self):
        c,o=self.fixture()
        for value in (False, None, 'true', True):
            o['a']=self.complete()
            o['a']['job']['layers'][0]['binding_decision']=dict(decision_source='policy_auto', action='bind',option_id='mesh_chain:l:arm',evidence_current=value)
            row=summarize(c,o)['characters'][0]
            self.assertEqual(row['completed'], value is True)
            self.assertEqual(row['stale_auto_layers'], [] if value is True else ['arm'])
            if value is not True:self.assertIn('automatic_binding_evidence_stale', row['reason_codes'])
