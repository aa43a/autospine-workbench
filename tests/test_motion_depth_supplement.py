import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from io import BytesIO
from zipfile import ZipFile
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_depth_supplement import validate, publish, summaries


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.files={'skeleton.json':b'{}'}
        self.depth={'pairs':[dict(arm_slot='arm',torso_slot='body',samples=[
            dict(tick=0,overlap=dict(status='sampled',overlap_pixels=4)),
            dict(tick=100000,overlap=dict(status='unmeasured'))])]}
        self.value=dict(candidate_sha256='a'*64,receipt=dict(depth_audit=dict(depth=self.depth)))
        self.report=dict(profile='conservative-triangle-box-tiles-v1-experiment',
            registration_sha256='b'*64,artifact_sha256='a'*64,
            skeleton_sha256=sha256(b'{}').hexdigest(),depth_sha256=sha256(canonical_bytes(self.depth)).hexdigest(),
            authority='none',production_authorized=False,common_measured=1,overlap_mismatches=0,
            recovered=1,lost_measurements=0,unmeasured=0,records=[
                dict(pair=['arm','body'],time=s['tick']/1e6,previous=s['overlap'],
                     current=dict(status='sampled',overlap_pixels=4)) for s in self.depth['pairs'][0]['samples']])

    def test_persistent_supplement_keeps_original_evidence(self):
        before=deepcopy(self.value)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            digest=publish(root,root/'job','b'*64,self.value,self.files,self.report)
            self.assertEqual(publish(root,root/'job','b'*64,self.value,self.files,self.report),digest)
            rows=summaries(root,root/'job','b'*64,self.value,self.files)
            self.assertEqual(rows[0]['recovered'],1)
            self.assertFalse(rows[0]['selected'])
            self.assertEqual(rows[0]['digest'],digest)
        self.assertEqual(self.value,before)

    def test_foreign_and_invented_summary_rejected(self):
        for key,value in [('registration_sha256','c'*64),('depth_sha256','c'*64),
                          ('artifact_sha256','c'*64),('recovered',3),('recovered',True),
                          ('production_authorized',True)]:
            r=deepcopy(self.report);r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate(r,'b'*64,self.value,self.files)

    def test_duplicate_missing_and_changed_previous_sample_rejected(self):
        for change in ('duplicate','missing','previous'):
            r=deepcopy(self.report)
            if change=='duplicate':r['records'][1]=r['records'][0]
            elif change=='missing':r['records'].pop()
            else:r['records'][0]['previous']['overlap_pixels']=99
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate(r,'b'*64,self.value,self.files)

    def test_lost_measurements_are_preserved_not_claimed_passed(self):
        r=deepcopy(self.report);r['records'][0]['current']=dict(status='unmeasured')
        r.update(common_measured=0,lost_measurements=1,unmeasured=1)
        result=validate(r,'b'*64,self.value,self.files)
        self.assertEqual(result['missing'],[dict(time=0,pair=['arm','body'])])
        self.assertEqual(result['lost_measurements'],1)

    def test_export_has_verified_supplement_and_unchanged_candidate(self):
        from autospine_workbench.automation.motion_related_export import package
        from autospine_workbench.automation.motion_related_evidence import bundle_digest
        from autospine_workbench.resolved_project import canonical_sha256
        candidate=bundle_digest(self.files)
        self.value.update(candidate_sha256=candidate,evidence=dict(candidate_sha256=candidate),
                          baseline_sha256='base',request_sha256='request',runtime={})
        self.report['artifact_sha256']=candidate
        readiness=dict(artifact_sha256=candidate,baseline_sha256='base',request_sha256='request',
            registration_sha256='b'*64,related_evidence_sha256=canonical_sha256(self.value['evidence']))
        stage=dict(artifact_sha256=candidate,registration_sha256='b'*64,readiness=readiness,
            evidence_sha256=canonical_sha256(readiness),authority='none',production_authorized=False,revision=1)
        raw=package(self.value,self.files,stage,[self.report])
        with ZipFile(BytesIO(raw)) as archive:
            manifest=json.loads(archive.read('related-export.json'))
            name=next(n for n in manifest['evidence_files'] if n.startswith('depth-supplements/'))
            self.assertEqual(json.loads(archive.read(name)),self.report)
            self.assertEqual(sha256(archive.read(name)).hexdigest(),manifest['evidence_files'][name])
            self.assertEqual(archive.read('skeleton.json'),self.files['skeleton.json'])
            self.assertEqual(json.loads(archive.read('related-stage-review.json')),stage)
        with self.assertRaises(ValueError):package(self.value,self.files,None,[self.report])
        bad=deepcopy(self.report);bad['registration_sha256']='c'*64
        with self.assertRaises(ValueError):package(self.value,self.files,stage,[bad])
