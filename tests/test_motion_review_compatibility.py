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

    def test_empty_geometry_extension_alone_or_with_projection(self):
        for projection_added in (False, True):
            old = deepcopy(self.old)
            old['stages'].append(dict(stage='几何', status='sampled_pass', failures=[]))
            new = deepcopy(old)
            if projection_added:
                new['stages'][0].update(unreliable_frames=[], failures=[], pose_profile=None)
            new['stages'][-1]['repair_limits'] = []
            current = dict(artifact_sha256='same', evidence_sha256=canonical_sha256(old))
            before = deepcopy(new)
            self.assertEqual(match(current, new, canonical_sha256(new)), 'legacy_empty_diagnostic_fields')
            self.assertEqual(new, before)
            from autospine_workbench.automation.motion_stage_review import _state
            state = _state('job', new, canonical_sha256(new), [current])
            self.assertTrue(state['current_applies'])
            self.assertEqual(state['current'], current)
            from m4_motion_cohort_reviews import decision
            current.update(decision='accepted_with_exceptions')
            self.assertEqual(decision(dict(cells={'cell':state}), 'cell',
                dict(job_id='job', result=dict(artifact_sha256='same')), new)[0], 'accepted_with_exceptions')

    def test_geometry_compatibility_rejects_nonempty_or_other_changes(self):
        old = deepcopy(self.new)
        old['stages'].append(dict(stage='几何', status='sampled_pass', failures=[]))
        current = dict(artifact_sha256='same', evidence_sha256=canonical_sha256(old))
        new = deepcopy(old); new['stages'][-1]['repair_limits'] = []
        mutations = [
            lambda r:r['stages'][-1].update(repair_limits=[{'triangle':3}]),
            lambda r:r['stages'][-1].update(repair_limits=None),
            lambda r:r['stages'][-1].update(status='needs_changes'),
            lambda r:r['stages'][-1].update(failures=[{'time':1}]),
            lambda r:r['stages'][-1].update(unknown=[]),
            lambda r:r['stages'].append(deepcopy(r['stages'][-1])),
            lambda r:r.update(scope='changed'),
        ]
        for mutate in mutations:
            report=deepcopy(new); mutate(report)
            self.assertEqual(match(current,report,canonical_sha256(report)),'evidence_changed')
