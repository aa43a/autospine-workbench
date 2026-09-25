import unittest
from autospine_workbench.targets.character43.deform_addition import value,runtime_union_times
from autospine_workbench.targets.character43.runtime_storage_reference import f32


class DeformRuntimeUnionTests(unittest.TestCase):
    def test_original_corner_is_preserved_when_correction_time_aliases_it(self):
        t=.100000001
        original=[dict(time=0,vertices=[0]),dict(time=t,vertices=[100]),dict(time=.2,vertices=[0])]
        correction=[dict(time=f32(t),vertices=[0]),dict(time=.15,vertices=[0])]
        times=runtime_union_times(original,correction)
        self.assertIn(t,times)
        self.assertEqual(len(times),len({f32(x) for x in times}))
        baked=[dict(time=x,vertices=value(original,x,1)) for x in times]
        for time in (t-1e-9,t,t+1e-9,.13,.17):
            self.assertAlmostEqual(value(baked,time,1)[0],value(original,time,1)[0],places=12)

    def test_existing_ambiguous_timeline_is_not_silently_repaired(self):
        with self.assertRaises(ValueError):runtime_union_times([{'time':1.},{'time':1.+1e-10}],[])


if __name__=='__main__':unittest.main()
