"""D4's 513-frame profile is explicit and cannot loosen historical 257 evidence."""
from copy import deepcopy
import unittest
from test_sleeve_contact_step import ContactStepTests
from test_sleeve_overlap_step import OverlapStepTests
from test_sleeve_motion_inventory import MotionInventoryTests
from test_sleeve_overlap_framebuffer import OverlapFramebufferTests
from autospine_workbench.automation.sleeve_motion_inventory import DEFORM,ORDINARY,PROFILES,frame_count
from autospine_workbench.targets.spine43.sleeve_framebuffer import summarize
from autospine_workbench.targets.spine43.sleeve_overlap_framebuffer import summaries as overlap_capture
from autospine_workbench.resolved_project import canonical_sha256

contact_fixture,contact_read=ContactStepTests.fixture,ContactStepTests.read
overlap_fixture,overlap_read=OverlapStepTests.fixture,OverlapStepTests.read
capture_fixture=MotionInventoryTests.fixture
pair_fixture=OverlapFramebufferTests.fixture
del ContactStepTests,OverlapStepTests,MotionInventoryTests,OverlapFramebufferTests


class DeformInventoryTests(unittest.TestCase):
    def test_profile_count_is_version_bound(self):
        row=dict(motion_profile=DEFORM,motion_source_sha256='b'*64)
        self.assertEqual(frame_count({'schema':'autospine.sleeve-export-report/v2'},row),513)
        self.assertEqual(frame_count({'schema':'autospine.sleeve-export-report/v1'},row),257)
        self.assertEqual(frame_count({'schema':'autospine.sleeve-export-report/v2'},row|dict(motion_profile=ORDINARY)),257)

    def test_contact_and_overlap_require_513_per_track(self):
        meta=dict(motion_profile=DEFORM,motion_source_sha256='b'*64)
        export,report=contact_fixture(self);export['schema']='autospine.sleeve-export-report/v2';export['records'][0].update(meta)
        report.update(schema='autospine.sleeve-contact-coverage/v2',source_sha256=canonical_sha256(export))
        report['records'][0].update(meta,tested_samples=2052,
            tracks=[dict(animation=n,frames=513,failed_samples=0) for n in PROFILES[DEFORM]])
        self.assertEqual(contact_read(self,export,report)['sleeve','part']['tested_samples'],2052)
        bad=deepcopy(report);bad['records'][0]['tracks'][0]['frames']=257
        with self.assertRaises(ValueError):contact_read(self,export,bad)
        export,report=overlap_fixture(self);export['schema']='autospine.sleeve-export-report/v2';export['records'][0].update(meta)
        report.update(schema='autospine.sleeve-overlap/v2',source_report_sha256=canonical_sha256(export))
        track=report['records'][0]['tracks'][0]
        report['records'][0].update(meta,tracks=[dict(track,animation=n,frames=513) for n in PROFILES[DEFORM]])
        self.assertEqual(overlap_read(self,export,report)['frames'],2052)
        bad=deepcopy(report);bad['records'][0]['tracks'][0]['frames']=257
        with self.assertRaises(ValueError):overlap_read(self,export,bad)

    def test_official_capture_513_inventory_and_old_rate_rejected(self):
        doc,contact=capture_fixture(self)
        doc['motion_profile']=contact['motion_profile']=DEFORM
        base=doc['frames'][0];doc['frames']=[];doc['captures']=[]
        for name in PROFILES[DEFORM]:
            doc['frames'] += [dict(base,animation=name,index=i,time=i/256) for i in range(513)]
            doc['captures'] += [dict(animation=name,index=i) for i in (0,128,256,384,512)]
        self.assertEqual(summarize(doc,contact)['frames'],2052)
        bad=deepcopy(doc);bad['frames'][1]['time']=1/128
        with self.assertRaises(ValueError):summarize(bad,contact)
        bad=deepcopy(doc);bad['frames'].pop()
        with self.assertRaises(ValueError):summarize(bad,contact)
        with self.assertRaises(ValueError):summarize(doc|dict(motion_profile=ORDINARY),contact|dict(motion_profile=ORDINARY))

    def test_overlap_peak_uses_quarter_tick_time(self):
        capture,source=pair_fixture(self)
        source.update(motion_profile=DEFORM,motion_source_sha256='b'*64)
        capture['captures'][1]['index']=128
        self.assertEqual(len(overlap_capture(capture,source)),1)
        capture['captures'][1]['index']=64
        with self.assertRaises(ValueError):overlap_capture(capture,source)


if __name__=='__main__':unittest.main()
