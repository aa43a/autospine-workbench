import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('build_m5_review', Path(__file__).parents[1]/'tools/build_m5_review.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class M5ReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mapping = dict(schema='autospine.m5-review-map/v1', base_url='http://127.0.0.1:8919', samples=[])
        for i, (character, motion) in enumerate((c, m) for c in module.CHARACTERS for m in module.MOTIONS):
            job = 'motion-'+format(i+1, '032x')
            folder = self.root/'jobs/motion-intake-v1'/job
            folder.mkdir(parents=True)
            execution = dict(parent_job_id='motion-'+'a'*32, parent_artifact_sha256='b'*64, config={}, duration=3)
            result = dict(artifact_sha256=format(i+1, '064x'), joint_animation_profile='joint-face-hair-cloth-v1',
                          joint_parent_job_id=execution['parent_job_id'], joint_parent_artifact_sha256='b'*64,
                          geometry_passed=True, joint_summary={}, runtime={'geometry_status': 'passed'})
            (folder/'request.json').write_text(json.dumps(dict(project_id=character, joint_execution=execution)))
            (folder/'result.json').write_text(json.dumps(dict(job_id=job, project_id=character, status='succeeded', result=result)))
            self.mapping['samples'].append(dict(character=character, motion=motion, job_id=job))

    def test_freezes_joint_only_without_m4_acceptance_and_escapes_script(self):
        snapshot = module.freeze(self.mapping, self.root)
        self.assertEqual(len(snapshot['samples']), 6)
        self.assertTrue(all(s['visual_status'] == 'not_evaluated' for s in snapshot['samples']))
        snapshot['samples'][0]['issues'] = ['</script><script>alert(1)</script>']
        html = module.render(snapshot)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('\\u003c/script>', html)

    def test_rejects_incomplete_cohort_and_changed_artifact(self):
        changed = json.loads(json.dumps(self.mapping))
        changed['samples'][0]['artifact_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'artifact_changed'):
            module.freeze(changed, self.root)
        self.mapping['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'exact_six'):
            module.freeze(self.mapping, self.root)

    def test_rejects_m4_only_result_and_wrong_project(self):
        row = self.mapping['samples'][0]
        row['project_id'] = 'another-character'
        with self.assertRaisesRegex(ValueError, 'project_mismatch'):
            module.freeze(self.mapping, self.root)
        del row['project_id']
        path = self.root/'jobs/motion-intake-v1'/row['job_id']/'result.json'
        value = json.loads(path.read_text())
        value['result'].pop('joint_animation_profile')
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'joint_result_required'):
            module.freeze(self.mapping, self.root)

    def test_rejects_pre_capture_result_and_keeps_body_effect_loop_separate(self):
        row = self.mapping['samples'][0]
        path = self.root/'jobs/motion-intake-v1'/row['job_id']/'result.json'
        value = json.loads(path.read_text())
        value['result']['runtime']['geometry_status'] = 'needs_changes'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'runtime_geometry_required'):
            module.freeze(self.mapping, self.root)
        value['result']['runtime']['geometry_status'] = 'passed'
        value['result']['joint_summary']['loop'] = dict(source_body={'loop_ready': False}, added_effects={'passed': True})
        path.write_text(json.dumps(value))
        result = module.freeze(self.mapping, self.root)['samples'][0]
        self.assertIs(result['loop']['source_body']['loop_ready'], False)
        self.assertIs(result['loop']['added_effects']['passed'], True)

    def acceptance(self):
        rows=[]
        for sample in self.mapping['samples']:
            folder=self.root/'jobs/motion-intake-v1'/sample['job_id']
            artifact=json.loads((folder/'result.json').read_bytes())['result']['artifact_sha256']
            readiness={'artifact_sha256':artifact,'status':'needs_changes'}
            digest=sha256(json.dumps(readiness,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            current=dict(schema='autospine.motion-stage-review/v1',job_id=sample['job_id'],artifact_sha256=artifact,
                evidence_sha256=digest,revision=1,decision='accepted_with_exceptions',notes='Keep technical limitations')
            (folder/'stage-reviews').mkdir()
            (folder/'stage-reviews/review-0001.json').write_text(json.dumps(current))
            rows.append(dict(**sample,artifact_sha256=artifact,readiness=readiness,evidence_sha256=digest,
                current=current,revision=1,current_applies=True,evidence_match='exact'))
        return rows

    def test_server_acceptance_requires_exact_evidence_and_separate_record(self):
        rows=self.acceptance()
        snapshot=module.freeze(self.mapping,self.root,rows)
        self.assertTrue(all(s['visual_status']=='accepted_with_exceptions' for s in snapshot['samples']))
        self.assertTrue(all(s['server_review']['revision']==1 for s in snapshot['samples']))
        self.assertIn('服务器阶段接受',module.render(snapshot))
        rows[0]['readiness']['status']='stage_review'
        with self.assertRaisesRegex(ValueError,'acceptance_evidence_mismatch'):
            module.freeze(self.mapping,self.root,rows)

    def test_server_acceptance_never_uses_stale_revision_or_local_draft(self):
        rows=self.acceptance()
        path=self.root/'jobs/motion-intake-v1'/rows[0]['job_id']/'stage-reviews/review-0001.json'
        value=json.loads(path.read_bytes());value['decision']='revoked';path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'server_record_mismatch'):
            module.freeze(self.mapping,self.root,rows)


if __name__ == '__main__':
    unittest.main()
