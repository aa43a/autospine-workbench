import unittest
from autospine_workbench.targets.character43.depth_partition_constraints import build


class PartitionConstraintTests(unittest.TestCase):
    def test_unknown_is_not_a_front_requirement_and_crossing_requires_validation(self):
        partition={'regions':[dict(source_slot='arm',slot='part',group='g')]}
        observations={'arm':[dict(body='body',time=i,source_tick=i*1000000) for i in range(6)]}
        result=build(partition,{'arm':{'groups':{'g':'FNAMUB'}}},observations)
        pair=result['pairs'][0]
        self.assertEqual([s['required_front'] for s in pair['samples']],['part',None,None,None,None,'body'])
        self.assertEqual(pair['transitions'],[dict(from_time=0,to_time=5,from_front='part',
            to_front='body',status='needs_interval_validation')])
        self.assertFalse(result['selected'])
        observations['arm'][-1]['time']=0
        with self.assertRaisesRegex(ValueError,'time_order'):
            build(partition,{'arm':{'groups':{'g':'FNAMUB'}}},observations)


if __name__=='__main__':unittest.main()
