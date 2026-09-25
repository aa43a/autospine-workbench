import unittest
from copy import deepcopy
from m4_runtime_batch_coverage import partition,verify,render_identity


class RuntimeBatchTests(unittest.TestCase):
    def batch(self,times):
        return dict(bundle_sha256='b',times=times,render_identity='render',geometry_passed=True,
            runtime=dict(bundle_sha256='b',passed=True,authority='none',production_authorized=False,
                results=[dict(time=t,animation='external-motion') for t in times],
                runtime_sha256='runtime',runtime_version='4.3.13',profile='official',browser_sha256='browser'))

    def test_full_grid_partitions_without_loss_or_budget_change(self):
        times=[i/14924 for i in range(14924)];chunks=partition(times)
        self.assertTrue(all(len(c)<=4097 for c in chunks))
        self.assertEqual(verify(times,[self.batch(c) for c in chunks])['frames'],14924)

    def test_missing_duplicate_and_changed_runtime_rejected(self):
        a=self.batch([0,.5]);b=self.batch([0,1])
        for batches in ([a],[a,a,b]):
            with self.assertRaises(ValueError):verify([0,.5,1],batches)
        b['runtime']['runtime_sha256']='changed'
        with self.assertRaises(ValueError):verify([0,.5,1],[a,b])
        b=self.batch([0,1]);b['runtime']['harness_sha256']='changed'
        with self.assertRaises(ValueError):verify([0,.5,1],[a,b])

    def test_only_declared_setup_anchor_may_repeat(self):
        self.assertTrue(verify([0,.5,1],[self.batch([0,.5]),self.batch([0,1])])['passed'])
        with self.assertRaises(ValueError):verify([0,.5,1],[self.batch([0,.5]),self.batch([0,.5,1])])

    def test_actual_result_times_and_geometry_must_match(self):
        a=self.batch([0,1]);a['runtime']['results'][1]['time']=.9
        with self.assertRaises(ValueError):verify([0,1],[a])
        a=self.batch([0,1]);a['geometry_passed']=False
        with self.assertRaises(ValueError):verify([0,1],[a])

    def test_texture_identity_is_independent_of_reference_chunks(self):
        files={'skeleton.json':b'{}','skeleton.atlas':b'atlas','textures/a.png':b'png','numeric-reference.json':b'one'}
        other=dict(files,**{'numeric-reference.json':b'two'})
        self.assertEqual(render_identity(files),render_identity(other))
        other['textures/a.png']=b'changed'
        self.assertNotEqual(render_identity(files),render_identity(other))


if __name__=='__main__':unittest.main()
