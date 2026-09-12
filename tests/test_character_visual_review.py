"""Explicit review does not become global visual or release authority."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from autospine_workbench.automation.character_visual_review import overview,save


class VisualReviewTests(unittest.TestCase):
    def test_review_validates_files_without_building_download(self):
        self.manager.download=Mock(side_effect=AssertionError('review must not allocate zip'))
        overview(self.manager,'p','j')
        self.manager.verified_files.assert_called_once_with('p','j')
        self.manager.download.assert_not_called()
        self.manager.verified_files.side_effect=RuntimeError('source mismatch')
        with self.assertRaisesRegex(RuntimeError,'source mismatch'):
            save(self.manager,'p','j',self.body)

    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        self.result=dict(status='needs_review',artifact_sha256='a'*64,runtime={'files':{'report.json':'b'*64}})
        self.manager=SimpleNamespace(_lock=RLock(),_path=lambda _:root,get=Mock(side_effect=lambda *_:self.result),
                                     verified_files=Mock(),review_file=Mock())
        self.body=dict(expected_artifact_sha256='a'*64,expected_review_sha256=None,
                       aspects=dict(setup='acceptable',draw_order='not_reviewed',connections='needs_changes',motion='acceptable'),notes='left wrist')

    def test_history_cas_and_correction(self):
        self.assertIsNone(overview(self.manager,'p','j')['review'])
        first=save(self.manager,'p','j',self.body)
        self.assertFalse(first['review']['production_authorized'])
        self.assertEqual(first['review']['aspects']['draw_order'],'not_reviewed')
        with self.assertRaisesRegex(RuntimeError,'conflict'):save(self.manager,'p','j',self.body)
        self.body['expected_review_sha256']=first['review_sha256'];self.body['aspects']['connections']='not_reviewed'
        second=save(self.manager,'p','j',self.body)
        self.assertEqual(second['review']['revision'],1)
        self.assertEqual(second['review']['previous_sha256'],first['review_sha256'])
        self.assertEqual(overview(self.manager,'p','j')['review_sha256'],second['review_sha256'])

    def test_no_report_stale_source_and_invalid_verdict_block_save(self):
        self.manager.review_file.side_effect=RuntimeError('missing capture')
        with self.assertRaisesRegex(RuntimeError,'missing capture'):save(self.manager,'p','j',self.body)
        self.manager.review_file.side_effect=None;self.result['status']='blocked'
        with self.assertRaisesRegex(RuntimeError,'preview_not_ready'):save(self.manager,'p','j',self.body)
        self.result['status']='needs_review';self.body['aspects']['motion']='approved'
        with self.assertRaisesRegex(RuntimeError,'invalid'):save(self.manager,'p','j',self.body)

    def test_changed_capture_or_cross_project_cannot_reuse_review(self):
        save(self.manager,'p','j',self.body)
        with self.assertRaisesRegex(RuntimeError,'source_mismatch'):overview(self.manager,'other','j')
        self.result['runtime']['files']['report.json']='c'*64
        with self.assertRaisesRegex(RuntimeError,'source_mismatch'):overview(self.manager,'p','j')

    def test_optional_timing_is_preserved_and_cannot_regress(self):
        timing=dict(method='operator_stopwatch_v1',scope='whole_character_visual_review_session',seconds=90.5)
        self.body['timing']=timing
        first=save(self.manager,'p','j',self.body)
        self.assertEqual(first['review']['timing'],timing)
        self.body['expected_review_sha256']=first['review_sha256'];self.body.pop('timing')
        second=save(self.manager,'p','j',self.body)
        self.assertEqual(second['review']['timing'],timing)
        self.body['expected_review_sha256']=second['review_sha256']
        self.body['timing']={**timing,'seconds':1}
        with self.assertRaisesRegex(RuntimeError,'regression'):save(self.manager,'p','j',self.body)
        for bad in (True,-1,float('nan'),86401):
            self.body['timing']={**timing,'seconds':bad}
            with self.assertRaisesRegex(RuntimeError,'invalid'):save(self.manager,'p','j',self.body)
