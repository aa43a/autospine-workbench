import unittest
from copy import deepcopy
from autospine_workbench.automation.sleeve_motion_inventory import motion_names,metadata,checked_names,ORDINARY,WIDE
from autospine_workbench.targets.spine43.sleeve_framebuffer import summarize


class MotionInventoryTests(unittest.TestCase):
    def test_legacy_is_always_seven_and_v2_rejects_unknown(self):
        row=dict(motion_profile=ORDINARY,motion_source_sha256='a'*64)
        self.assertEqual(len(motion_names({'schema':'autospine.sleeve-export-report/v1'},row)),7)
        export={'schema':'autospine.sleeve-export-report/v2'}
        self.assertEqual(len(motion_names(export,row)),4)
        self.assertEqual(metadata({'schema':'autospine.sleeve-export-report/v1'},row),{})
        for change in (dict(motion_profile='future'),dict(motion_source_sha256='invalid')):
            with self.assertRaises(ValueError): motion_names(export,row|change)
        with self.assertRaises(ValueError):checked_names(export,row,row|dict(motion_source_sha256='b'*64))

    def fixture(self):
        row=dict(motion_profile=ORDINARY,motion_source_sha256='a'*64)
        doc=dict(schema='autospine.sleeve-framebuffer/v2',authority='none',production_authorized=False,status='needs_review',
                 scope='isolated_sleeve_native_pixel_contact_probes',runtime_package='@esotericsoftware/spine-webgl',
                 runtime_version='4.3.13',export_target='4.3.26',info=dict(probe_count=1),frames=[],captures=[],**row)
        for name in motion_names({'schema':'autospine.sleeve-export-report/v2'},row):
            doc['frames'] += [dict(animation=name,index=i,time=i/128,tested_samples=1,failed_samples=0,
                visible_pixels=10,min_alpha=255,max_error_px=0,failures=[]) for i in range(257)]
            doc['captures'] += [dict(animation=name,index=i) for i in (0,64,128,192,256)]
        return doc,dict(interfaces=[dict(samples=[1])],**row)

    def test_four_track_capture_requires_v2_exact_profile_and_full_inventory(self):
        doc,contact=self.fixture()
        self.assertEqual(summarize(doc,contact)['frames'],1028)
        for change in (dict(schema='autospine.sleeve-framebuffer/v1'),dict(motion_profile=WIDE),dict(motion_profile='unknown')):
            with self.assertRaises(ValueError):summarize(doc|change,contact)
        changed=deepcopy(doc);changed['frames'].pop()
        with self.assertRaises(ValueError):summarize(changed,contact)
        with self.assertRaises(ValueError):summarize(doc,contact|dict(motion_source_sha256='b'*64))
