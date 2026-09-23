import json
import unittest
from urllib.parse import unquote,urlsplit
from m4_motion_review_pack import url
from m4_motion_cohort import digest


class ReviewPackTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(motions=[dict(id='wave',sha256='s'*64)],characters=[dict(id='alice')])
        self.state=dict(plan_sha256=digest(self.plan),sources=dict(wave=dict(status='succeeded',
            source_sha256='s'*64,job_id='motion-source')),cells={'wave/alice':dict(status='succeeded',
            job_id='motion-target',result=dict(artifact_sha256='a'*64))})

    def test_exact_job_and_artifact_in_navigation_only(self):
        value=urlsplit(url(self.plan,self.state))
        self.assertEqual(value.path,'/motion-cohort.html')
        pack=json.loads(unquote(value.fragment))
        self.assertEqual(pack['groups'][0]['targets'],[dict(label='alice',job_id='motion-target',artifact_sha256='a'*64)])
        self.assertNotIn('decision',str(pack))

    def test_mismatched_source_or_plan_rejected(self):
        self.state['sources']['wave']['source_sha256']='other'
        with self.assertRaisesRegex(ValueError,'source_mismatch'):url(self.plan,self.state)
        self.state['plan_sha256']='other'
        with self.assertRaisesRegex(ValueError,'plan_identity'):url(self.plan,self.state)

    def test_incomplete_candidates_do_not_get_review_links(self):
        self.state['cells']['wave/alice']['status']='running'
        self.assertIsNone(url(self.plan,self.state))

    def test_missing_and_failed_cells_remain_in_denominator(self):
        self.plan['characters'].append(dict(id='huiye'))
        self.plan['motions'].append(dict(id='reach',sha256='r'*64))
        self.state['plan_sha256']=digest(self.plan)
        self.state['sources']['reach']=dict(status='failed')
        self.state['cells']['wave/huiye']=dict(status='running')
        pack=json.loads(unquote(urlsplit(url(self.plan,self.state)).fragment))
        self.assertEqual(pack['coverage']['expected'],4)
        self.assertEqual(pack['coverage']['available'],1)
        self.assertEqual(pack['coverage']['missing'],[
            dict(motion='wave',character='huiye',status='running'),
            dict(motion='reach',character='alice',status='source_failed'),
            dict(motion='reach',character='huiye',status='source_failed')])


if __name__=='__main__':unittest.main()
