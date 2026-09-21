import unittest
from copy import deepcopy
from autospine_workbench.targets.character43.depth_temporal_labels import stabilize


class TemporalLabelTests(unittest.TestCase):
    mesh={'triangles':[0,1,2]}
    def rows(self,states,labels):
        return [dict(time=i,source_tick=i,observed_states=s,labels=[v]) for i,(s,v) in enumerate(zip(states,labels))]

    def test_future_evidence_removes_ambiguous_flicker(self):
        models={'body':self.rows('FAAAF',[1,0,1,0,1])}
        result=stabilize(self.mesh,models,[],'arm',{'body':True})
        self.assertEqual([f['labels'][0] for f in models['body']],[1]*5)
        self.assertEqual(result['changed_labels'],2)
        self.assertEqual(''.join(f['observed_states'] for f in models['body']),'FAAAF')

    def test_real_hard_reversal_and_unknown_gap_remain(self):
        models={'body':self.rows('FANUB',[1,1,0,0,0])}
        stabilize(self.mesh,models,[],'arm',{'body':False})
        self.assertEqual([f['labels'][0] for f in models['body']],[1,1,0,0,0])

    def test_ambiguous_island_has_no_fabricated_hard_anchor(self):
        models={'body':self.rows('NAN',[0,1,0])}
        stabilize(self.mesh,models,[],'arm',{'body':False})
        self.assertEqual(models['body'][1]['labels'],[1])

    def test_hard_neighbours_cannot_be_changed(self):
        mesh={'triangles':[0,1,2,2,1,3]}
        models={'body':[dict(time=i,source_tick=i,observed_states='AF',labels=[0,1]) for i in range(3)]}
        stabilize(mesh,models,[],'arm',{'body':False})
        self.assertTrue(all(f['labels']==[1,1] for f in models['body']))

    def test_back_anchors_fix_an_ambiguous_front_island(self):
        models={'body':self.rows('BAB',[0,1,0])}
        stabilize(self.mesh,models,[],'arm',{'body':False})
        self.assertEqual([f['labels'][0] for f in models['body']],[0,0,0])

    def test_only_identical_plane_evidence_connects_bodies(self):
        initial={'a':self.rows('FA',[1,0]),'b':self.rows('NA',[0,0])}
        evidence=dict(profile='torso-anchored-planar-garment-depth-v1-experiment',coefficients=[0,0,0],anchors={})
        checks=[dict(arm='arm',body=b,time=1,source_tick=1,reference_plane=[0,0,0],
                     reference_plane_evidence=deepcopy(evidence)) for b in initial]
        models=deepcopy(initial);stabilize(self.mesh,models,checks,'arm',{'a':False,'b':False})
        self.assertEqual(models['b'][1]['labels'],[1])
        checks[1]['reference_plane_evidence']['anchors']={'different':1}
        models=deepcopy(initial);stabilize(self.mesh,models,checks,'arm',{'a':False,'b':False})
        self.assertEqual(models['b'][1]['labels'],[0])
