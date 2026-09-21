from copy import deepcopy
import unittest
from m4_regional_sampling_compare import compare


class SamplingCompareTests(unittest.TestCase):
    def fixture(self):
        return dict(source_job='job',source_artifact_sha256='artifact',request_sha256='request',motion_identity={},
            depth=dict(regional=dict(refinement=dict(rows=[dict(pair=['a','b'],tick=0,checks=[
                dict(time=0,status='no_overlap'),dict(time=.5,status='unmeasured')])]))))

    def test_recovery_preserves_inventory_and_measured_values(self):
        before=self.fixture();after=deepcopy(before)
        after['depth']['regional']['refinement']['rows'][0]['checks'][1]['status']='no_overlap'
        result=compare(before,after)
        self.assertEqual(result['recovered_samples'],1)
        self.assertEqual(result['preserved_measured_samples'],1)
        self.assertFalse(result['adoption_allowed'])

    def test_changed_or_dropped_old_measurement_rejected(self):
        for mode in ('drop','change','identity'):
            before=self.fixture();after=deepcopy(before)
            checks=after['depth']['regional']['refinement']['rows'][0]['checks']
            if mode=='drop':checks.pop()
            elif mode=='change':checks[0]['status']='unmeasured'
            else:after['source_artifact_sha256']='other'
            with self.assertRaises(ValueError):compare(before,after)
