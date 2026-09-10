import unittest
try:import numpy as np
except ImportError:np=None
from autospine_workbench.targets.spine43.sleeve_contact_samples import probes,coverage,analyze


@unittest.skipIf(np is None,'optional NumPy analysis dependency is unavailable')
class SleeveContactTests(unittest.TestCase):
    def fixture(self):
        attachment=dict(triangles=[0,1,2,1,3,2],uvs=[0,0,1,0,0,1,1,1])
        points=[[0,0],[16,0],[0,-16],[16,-16]]
        roles=[dict(role='cuff'),dict(role='hand')]
        return attachment,points,roles,np.full((16,16),255.)

    def test_shared_interface_opaque_texture_and_pixel_coverage(self):
        attachment,points,roles,alpha=self.fixture();interfaces=probes(attachment,roles,alpha)
        self.assertEqual(len(interfaces),1);self.assertEqual(len(interfaces[0]['samples']),3)
        self.assertEqual(coverage(attachment,points,alpha,[[8,8],[40,40]]),[255.,0.])
        result=analyze(attachment,alpha,interfaces,{'pose':[dict(time=0,points=points)]})
        self.assertEqual(result['status'],'cpu_coverage_passed');self.assertEqual(result['framebuffer_status'],'not_evaluated')
        self.assertIs(result['production_authorized'],False)

    def test_source_transparency_is_unobservable_not_false_pass(self):
        attachment,points,roles,alpha=self.fixture();alpha[:]=0
        result=analyze(attachment,alpha,probes(attachment,roles,alpha),{'pose':[dict(time=0,points=points)]})
        self.assertEqual(result['status'],'needs_review');self.assertEqual(result['tested_samples'],0)
        self.assertEqual(result['unobservable_interfaces'],1)

    def test_missing_dynamic_alpha_is_measured_as_failure(self):
        attachment,points,roles,alpha=self.fixture();interfaces=probes(attachment,roles,alpha)
        result=analyze(attachment,np.zeros_like(alpha),interfaces,{'pose':[dict(time=0,points=points)]})
        self.assertEqual(result['failed_samples'],3);self.assertEqual(result['status'],'needs_review')

    def test_bad_assignment_and_nonmanifold_edge_fail_closed(self):
        attachment,points,roles,alpha=self.fixture()
        with self.assertRaisesRegex(ValueError,'inventory'):probes(attachment,[],alpha)
        attachment['triangles'] += [1,3,2]
        with self.assertRaisesRegex(ValueError,'nonmanifold'):probes(attachment,roles+[dict(role='hand')],alpha)

    def test_length_sampling_finds_short_opaque_contact_without_relaxing_margin(self):
        attachment,_,roles,_=self.fixture()
        alpha=np.zeros((64,64));alpha[5:12,52:59]=255
        self.assertEqual(probes(attachment,roles,alpha)[0]['samples'],[])
        samples=probes(attachment,roles,alpha,profile='source-length-v2')[0]['samples']
        self.assertGreater(len(samples),0)
        self.assertTrue(all(s['source_min_alpha']==255 for s in samples))
        enlarged=np.repeat(np.repeat(alpha,2,axis=0),2,axis=1)
        self.assertGreater(len(probes(attachment,roles,enlarged,profile='source-length-v2')[0]['samples']),len(samples))
        alpha[:]=0;alpha[8,55]=255
        self.assertEqual(probes(attachment,roles,alpha,profile='source-length-v2')[0]['samples'],[])

    def test_length_sampling_keeps_transparent_interfaces_unobservable(self):
        attachment,points,roles,alpha=self.fixture();alpha[:]=0
        interfaces=probes(attachment,roles,alpha,profile='source-length-v2')
        self.assertEqual(interfaces[0]['observability'],'source_alpha_unobservable')
        with self.assertRaisesRegex(ValueError,'probe_profile'):probes(attachment,roles,alpha,profile='unknown')
