from copy import deepcopy
from hashlib import sha256
import unittest
from test_limb_transverse_repair import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.character43.boundary_curve_sources import read_compensation,resample_margins


class BoundaryCurveSourcesTests(unittest.TestCase):
    def test_interpolates_targets_at_new_keys_preserving_zero_gaps(self):
        margins={1.:[.02,.01]};original=deepcopy(margins)
        result=resample_margins(margins,[0.,1.,2.],[0.,.5,1.,1.5,2.],2)
        self.assertEqual(result[0.],[0.,0.]);self.assertEqual(result[2.],[0.,0.])
        self.assertEqual(result[.5],[.01,.005]);self.assertEqual(result[1.],margins[1.])
        self.assertEqual(result[1.5],[.01,.005]);self.assertEqual(margins,original)

    def test_rejects_target_extrapolation_alias_and_invalid_margin(self):
        for times in ([-1.,0.,1.],[0.,1.,1.],[0.,float('nan')]):
            with self.assertRaises(ValueError):resample_margins({},[0.,1.],times,1)
        for margins in ({.5:[0.]},{0.:[.03]},{0.:[float('nan')]},{0.:[]}):
            with self.assertRaises(ValueError):resample_margins(margins,[0.,1.],[0.,1.],1)

    def test_refined_source_requires_identity_success_and_unchanged_other_content(self):
        parent=fixture();candidate,_=build(parent,'motion',['leg']);raw=canonical_bytes(candidate)
        report=dict(profile='fixed-surface-adaptive-sampling-v1-experiment',status='sampled_fixed_floors_passed',
            parent_artifact_sha256='parent',slot='leg',skeleton_sha256=sha256(raw).hexdigest(),history=[{'failures':[]}])
        self.assertEqual(read_compensation(parent,raw,report,'parent','leg','motion'),candidate)
        for field,value in (('status','round_limit'),('slot','other'),('skeleton_sha256','wrong'),('history',[{'failures':[1]}])):
            invalid=dict(report,**{field:value})
            with self.assertRaises(ValueError):read_compensation(parent,raw,invalid,'parent','leg','motion')
        changed=deepcopy(candidate);changed['bones'][0]['x']=8;raw=canonical_bytes(changed)
        report['skeleton_sha256']=sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'unrelated'):read_compensation(parent,raw,report,'parent','leg','motion')
