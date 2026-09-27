from copy import deepcopy
import math
import unittest
from autospine_workbench.targets.character43.moving_ankle_candidate import build
from autospine_workbench.targets.character43.affine_pose import matrices


def fixture():
    bones = [dict(name='root', x=0, y=0, rotation=0)]
    for side, x in [('l', -5), ('r', 5)]:
        bones.extend([dict(name='thigh_'+side,parent='root',x=x,y=0,rotation=-70),
                      dict(name='calf_'+side,parent='thigh_'+side,x=10,y=0,rotation=-30),
                      dict(name='foot_'+side,parent='calf_'+side,x=10,y=0,rotation=0)])
    doc = dict(bones=bones, animations={'move':{'bones':{'root':{'translate':[
        dict(time=0,x=0,y=0),dict(time=1,x=0,y=0)]}}}})
    initial = matrices(doc,'move',0)
    points = [list(initial['foot_'+s][4:6]) for s in ('l','r')]
    return doc, [dict(time=0,targets=points), dict(time=1,targets=[
        [p[0]+.2,p[1]+.1] for p in points])]


class MovingAnkleTests(unittest.TestCase):
    def test_roundoff_aliases_produce_distinct_runtime_keys(self):
        from autospine_workbench.targets.character43.runtime_storage_reference import f32, require_distinct_times
        doc,trajectory=fixture()
        candidate,report=build(doc,'move',trajectory,[0,.21484375,.21484375000000003,1],20)
        self.assertIsNotNone(candidate)
        self.assertEqual(len(report['merged_time_aliases']),1)
        self.assertEqual(report['required_knots'],3)
        for row in candidate['animations']['move']['bones'].values():
            for keys in row.values():
                require_distinct_times([dict(time=f32(k['time'])) for k in keys])

    def test_distinct_events_are_not_silently_merged(self):
        from autospine_workbench.targets.character43.moving_ankle_candidate import timeline_union
        with self.assertRaisesRegex(ValueError,'distinct_times_collide'):
            timeline_union([0,1],[],[.5,.50000001])

    def test_source_endpoint_is_retained_over_sampling_alias(self):
        from autospine_workbench.targets.character43.moving_ankle_candidate import timeline_union
        endpoint=.9882812500000001
        source=[0,endpoint]; tracks=[0,.98828125]
        knots,aliases=timeline_union(source,tracks,[.5])
        self.assertEqual(knots,[0,.5,endpoint])
        self.assertEqual(aliases[0]['retained_time'],endpoint)
        self.assertEqual(source,[0,endpoint])
        self.assertEqual(tracks,[0,.98828125])

    def test_distinct_source_observations_are_never_merged(self):
        from autospine_workbench.targets.character43.moving_ankle_candidate import timeline_union
        with self.assertRaisesRegex(ValueError,'distinct_times_collide'):
            timeline_union([0,.5,math.nextafter(.5,1),1],[],[])

    def test_moving_targets_preserved_without_mutating_source(self):
        doc, trajectory = fixture(); before = deepcopy((doc,trajectory))
        candidate, report = build(doc,'move',trajectory,[0,.5,1],20)
        self.assertIsNotNone(candidate)
        self.assertFalse(report['selected'])
        self.assertEqual([r['time'] for r in report['rows']],[0,.5,1])
        pose = matrices(candidate,'move',1)
        for i,s in enumerate(('l','r')):
            self.assertLessEqual(math.dist(pose['foot_'+s][4:6],trajectory[-1]['targets'][i]),.2)
        self.assertEqual((doc,trajectory),before)
        self.assertEqual(candidate['bones'],doc['bones'])

    def test_infeasible_frame_does_not_return_partial_candidate(self):
        doc, trajectory = fixture(); before = deepcopy(doc)
        trajectory[-1]['targets'] = [[10000,0],[10000,0]]
        candidate, report = build(doc,'move',trajectory,[0,.5,1],20)
        self.assertIsNone(candidate)
        self.assertEqual(report['status'],'blocked')
        self.assertIn('endpoint_residual',report['failure']['failed_checks'])
        self.assertEqual(doc,before)

    def test_invalid_target_time_rejected(self):
        doc, trajectory = fixture();trajectory[-1]['time']=0
        with self.assertRaisesRegex(ValueError,'trajectory_invalid'):
            build(doc,'move',trajectory,[0,1],20)
