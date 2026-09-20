import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from types import SimpleNamespace
from autospine_workbench.automation.motion_target_comparison import signature, recommend, inspect


class TargetComparisonTests(unittest.TestCase):
    def test_inventory_excludes_other_character_and_keeps_outdated_candidates(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name,rig in [('motion-a','rig'),('motion-b','rig'),('motion-c','other')]:
                folder=root/name; folder.mkdir()
                (folder/'request.json').write_bytes(canonical_bytes(dict(kind='adapt',job_id=name,
                    source_job_id='source',character_sha256=rig)))
            def get(job):
                return (dict(job_id=job,source_sha256='raw',format='fbx',view='front') if job=='source'
                        else dict(status='outdated' if job=='motion-b' else 'succeeded'))
            manager=SimpleNamespace(root=root,folder=lambda job:root/job,get=get)
            with patch('autospine_workbench.automation.motion_target_comparison.stage_review',return_value=dict(
                    current=None,current_applies=False,artifact_sha256='artifact',evidence_sha256='evidence',
                    readiness=dict(status='stage_review',stages=[]))) as review:
                result=inspect(manager,'motion-a')
            self.assertEqual(result['matching_candidates'],2)
            self.assertEqual(result['recommended_job_id'],'motion-a')
            self.assertEqual(result['rows'][1]['status'],'outdated')
            review.assert_called_once_with(manager,'motion-a')

    def test_same_bytes_and_rig_but_different_views_match(self):
        jobs = {'a': dict(source_sha256='raw', format='fbx', view='front'),
                'b': dict(source_sha256='raw', format='fbx', view='side')}
        manager = SimpleNamespace(get=jobs.__getitem__)
        a = dict(source_job_id='a', character_sha256='rig', clip=None, contact_correction=True)
        b = dict(a, source_job_id='b', projection={'yaw_degrees':30})
        self.assertEqual(signature(manager,a), signature(manager,b))
        for change in ({'clip':{'start_frame':3}}, {'character_sha256':'other'},
                       {'contact_correction':False}, {'depth_review_profile':'new'}):
            self.assertNotEqual(signature(manager,a), signature(manager,dict(b,**change)))
        jobs['b']['result']={'fps':60}
        self.assertNotEqual(signature(manager,a), signature(manager,b))
        del jobs['b']['result']
        jobs['b']['source_sha256']='changed'
        self.assertNotEqual(signature(manager,a), signature(manager,b))

    def test_rejected_incomplete_and_failing_candidates_are_not_recommended(self):
        good = dict(job_id='good', readiness='stage_review', visual_decision='not_reviewed')
        rows = [dict(good,job_id='bad',readiness='needs_changes'),
                dict(good,job_id='rejected',visual_decision='rejected'),
                dict(good,job_id='stale',visual_decision='evidence_changed')]
        self.assertIsNone(recommend(rows,complete=True))
        self.assertEqual(recommend(rows+[good],complete=True),'good')
        self.assertIsNone(recommend(rows+[good],complete=False))
        accepted=dict(good,job_id='accepted',visual_decision='accepted')
        self.assertEqual(recommend([good,accepted],complete=True),'accepted')


if __name__=='__main__': unittest.main()
