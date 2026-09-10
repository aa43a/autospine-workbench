import unittest
from copy import deepcopy
from autospine_workbench.targets.spine43.sleeve_framebuffer import summarize
from autospine_workbench.asset.planning.sleeve_motion_envelope import MOTIONS


class FramebufferTests(unittest.TestCase):
    def fixture(self):
        doc=dict(schema='autospine.sleeve-framebuffer/v1',authority='none',production_authorized=False,status='needs_review',
            scope='isolated_sleeve_native_pixel_contact_probes',runtime_package='@esotericsoftware/spine-webgl',
            runtime_version='4.3.13',export_target='4.3.26',info=dict(probe_count=1),frames=[],captures=[])
        for n,_ in MOTIONS:
            doc['frames'] += [dict(animation=n,index=i,time=i/128,tested_samples=1,failed_samples=0,
                visible_pixels=12,min_alpha=255,max_error_px=0,failures=[]) for i in range(257)]
            doc['captures'] += [dict(animation=n,index=i) for i in (0,64,128,192,256)]
        return doc,dict(interfaces=[dict(samples=[1])])

    def test_complete_capture_preserves_scope(self):
        summary=summarize(*self.fixture())
        self.assertEqual(summary['frames'],1799)
        self.assertEqual(summary['overlap_status'],'not_evaluated')
        self.assertIs(summary['production_authorized'],False)

    def test_missing_duplicate_wrong_pose_empty_and_authority_fail(self):
        doc,contact=self.fixture()
        mutations=[lambda d:d['frames'].pop(),lambda d:d['frames'].append(d['frames'][0]),
            lambda d:d['frames'][0].update(max_error_px=.01),lambda d:d['frames'][0].update(visible_pixels=0),
            lambda d:d['frames'][0].update(failed_samples=1),lambda d:d.update(production_authorized=True),
            lambda d:d.update(captures=[])]
        for change in mutations:
            value=deepcopy(doc);change(value)
            with self.assertRaises(ValueError):summarize(value,contact)

    def test_actual_failed_probe_remains_failure(self):
        doc,contact=self.fixture();doc['frames'][0].update(min_alpha=0,failed_samples=1,failures=[dict(alpha=0)])
        self.assertEqual(summarize(doc,contact)['status'],'needs_review')
