import unittest
from autospine_workbench.targets.character43.depth_bracket_hysteresis import apply


class BracketHysteresisTests(unittest.TestCase):
    def run_case(self,states,labels):
        rows=[dict(time=i,observed_states=s,labels=[v]) for i,(s,v) in enumerate(zip(states,labels))]
        result=apply({'triangles':[0,1,2]},{'body':rows},{'body':False})
        return rows,result

    def test_matching_brackets_hold_only_ambiguous_span(self):
        rows,r=self.run_case('FAAF',[1,0,1,1])
        self.assertEqual([x['labels'][0] for x in rows],[1,1,1,1])
        self.assertEqual(''.join(x['observed_states'] for x in rows),'FAAF')
        self.assertEqual(r['changed_labels'],1)
        self.assertEqual(r['runs'][0]['changed_indices'],[1])

    def test_opposite_brackets_keep_inferred_transition(self):
        rows,r=self.run_case('FAAB',[1,1,0,0])
        self.assertEqual([x['labels'][0] for x in rows],[1,1,0,0])
        self.assertEqual(r['run_counts'],{'opposite_hard_brackets':1})

    def test_unknown_or_absent_brackets_are_not_bridged(self):
        for states in ('FANAF','FAUAF','FAMAF','AAAF','FAAA'):
            labels=[int(s=='F') for s in states];rows,r=self.run_case(states,labels)
            self.assertEqual([x['labels'][0] for x in rows],labels)
            self.assertEqual(r['changed_labels'],0)

    def test_back_bracket_does_not_flip_hard_evidence(self):
        rows,r=self.run_case('BAB',[0,1,0])
        self.assertEqual([x['labels'][0] for x in rows],[0,0,0])
        self.assertEqual(r['runs'][0]['bracket_state'],'B')

    def test_neighbouring_triangles_keep_different_temporal_cases(self):
        rows=[dict(time=i,observed_states=s,labels=v) for i,(s,v) in enumerate(
            [('FF',[1,1]),('AA',[0,1]),('FB',[1,0])])]
        result=apply({'triangles':[0,1,2,2,1,3]},{'body':rows},{'body':False})
        self.assertEqual(rows[1]['labels'],[1,1])
        self.assertEqual(rows[2]['labels'],[1,0])
        self.assertEqual(result['run_counts'],{'same_hard_brackets':1,'opposite_hard_brackets':1})
