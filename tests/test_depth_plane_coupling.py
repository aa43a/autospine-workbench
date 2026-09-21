import copy
import unittest
from autospine_workbench.targets.character43.depth_plane_coupling import couple


class PlaneCouplingTests(unittest.TestCase):
    def fixture(self, states=('A','A'), labels=(0,1)):
        mesh={'triangles':[0,1,2]}
        models={b:[dict(time=0,source_tick=0,observed_states=s,labels=[v],energy=0)]
                for b,s,v in zip(('a','b'),states,labels)}
        evidence=dict(profile='torso-anchored-planar-garment-depth-v1-experiment',coefficients=[0,0,0],anchors={})
        checks=[dict(arm='arm',body=b,time=0,source_tick=0,reference_plane=[0,0,0],
                     reference_plane_evidence=copy.deepcopy(evidence)) for b in models]
        return mesh,models,checks

    def test_ambiguous_disagreement_is_softly_unified(self):
        mesh,models,checks=self.fixture()
        records=couple(mesh,models,checks,'arm')
        self.assertEqual(models['a'][0]['labels'],models['b'][0]['labels'])
        self.assertEqual(records[0]['changed_labels'],1)
        self.assertEqual(models['a'][0]['observed_states'],'A')
        self.assertEqual(models['b'][0]['independent_labels'],[1])

    def test_hard_evidence_and_unknown_are_never_overridden(self):
        for state in ('F','B','U','M','N'):
            mesh,models,checks=self.fixture((state,'A'))
            before=copy.deepcopy(models)
            self.assertEqual(couple(mesh,models,checks,'arm'),[])
            for body in models:
                self.assertEqual(models[body][0]['labels'],before[body][0]['labels'])
                self.assertEqual(models[body][0]['observed_states'],before[body][0]['observed_states'])

    def test_plane_identity_includes_anchors_and_source_time(self):
        for change in ('anchors','source_tick','coefficients'):
            mesh,models,checks=self.fixture()
            if change=='source_tick':checks[1][change]=1
            else:checks[1]['reference_plane_evidence'][change]=[1]
            self.assertEqual(couple(mesh,models,checks,'arm'),[])

    def test_duplicate_receipt_fails(self):
        mesh,models,checks=self.fixture()
        with self.assertRaisesRegex(ValueError,'duplicate_check'):
            couple(mesh,models,checks+checks[:1],'arm')

    def test_opposing_hard_neighbours_remain_fixed(self):
        mesh,models,checks=self.fixture()
        mesh['triangles'] += [2,1,3]
        for body,state,label in [('a','F',1),('b','B',0)]:
            models[body][0]['observed_states'] += state
            models[body][0]['labels'].append(label)
        couple(mesh,models,checks,'arm')
        self.assertEqual(models['a'][0]['labels'][1],1)
        self.assertEqual(models['b'][0]['labels'][1],0)

    def test_transition_counts_include_the_next_uncoupled_frame(self):
        mesh,models,checks=self.fixture()
        for body in models:
            models[body].append(dict(time=1,source_tick=1,observed_states='F',labels=[1],energy=0))
        couple(mesh,models,checks,'arm',{'a':False,'b':True})
        for body in models:
            first,last=models[body]
            self.assertEqual(last['transition_count'],int(first['labels'][0]!=1))


if __name__=='__main__':unittest.main()
