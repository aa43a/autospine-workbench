from copy import deepcopy
import unittest
from autospine_workbench.automation.motion_review_compatibility import match
from autospine_workbench.resolved_project import canonical_sha256


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.old=dict(profile='external-motion-readiness-v1',artifact_sha256='same',status='needs_changes',
            stages=[dict(stage='投影',status='sampled_pass',reasons=[]),dict(stage='遮挡',status='needs_changes')])
        self.review=dict(artifact_sha256='same',evidence_sha256=canonical_sha256(self.old))
        self.new=deepcopy(self.old)
        self.new['stages'][0].update(unreliable_frames=[],failures=[],pose_profile=None)

    def check(self, report):
        return match(self.review,report,canonical_sha256(report))

    def test_only_additive_empty_projection_fields_are_compatible(self):
        self.assertEqual(self.check(self.old),'exact')
        before=deepcopy(self.new)
        self.assertEqual(self.check(self.new),'legacy_empty_projection_fields')
        self.assertEqual(self.new,before)
        self.assertEqual(self.review['evidence_sha256'],canonical_sha256(self.old))

    def test_real_or_unknown_changes_cannot_reuse_acceptance(self):
        for key,value in [('unreliable_frames',[{'time':1}]),('failures',[{'time':1}]),('pose_profile','new-profile'),('new_check',True),('explanation','changed')]:
            report=deepcopy(self.new);report['stages'][0][key]=value
            self.assertEqual(self.check(report),'evidence_changed',key)
        for key,value in [('profile','unknown'),('status','stage_review')]:
            report=deepcopy(self.new);report[key]=value
            self.assertEqual(self.check(report),'evidence_changed',key)
        report=deepcopy(self.new);report['stages'][1]['status']='sampled_pass'
        self.assertEqual(self.check(report),'evidence_changed')
        report=deepcopy(self.new);report['artifact_sha256']='other'
        self.assertEqual(self.check(report),'artifact_changed')

    def test_unknown_legacy_digest_missing_or_duplicate_stage_refused(self):
        self.review['evidence_sha256']='unknown'
        self.assertEqual(self.check(self.new),'evidence_changed')
        self.review['evidence_sha256']=canonical_sha256(self.old)
        for mutate in (lambda r:r['stages'].append(deepcopy(r['stages'][0])),lambda r:r['stages'][0].pop('failures')):
            report=deepcopy(self.new);mutate(report)
            self.assertEqual(self.check(report),'evidence_changed')

    def test_fixed_cohort_uses_same_compatibility_without_trusting_flag_alone(self):
        from m4_motion_cohort_reviews import decision
        current=dict(self.review,decision='accepted_with_exceptions')
        row=dict(job_id='job',artifact_sha256='same',evidence_sha256=canonical_sha256(self.new),current=current,current_applies=True)
        snapshot=dict(cells={'cell':row});job=dict(job_id='job',result=dict(artifact_sha256='same'))
        self.assertEqual(decision(snapshot,'cell',job,self.new)[0],'accepted_with_exceptions')
        changed=deepcopy(self.new);changed['stages'][0]['failures']=[dict(time=1)]
        row['evidence_sha256']=canonical_sha256(changed)
        self.assertEqual(decision(snapshot,'cell',job,changed)[0],'evidence_changed')
