from copy import deepcopy
from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from autospine_workbench.automation.character_stage_defaults import evaluate, read, PROFILE, LEGACY_PROFILE
from autospine_workbench.automation.storage_io import canonical_bytes


def fixture():
    layer=dict(layer_id='arms',name='handwear',state='weighted_candidate',missing_region_ids=[],
        binding_decision=dict(decision_source='pending',action='pending'),
        regions=[dict(region_id='arms-'+s,state='weighted_candidate') for s in ('l','r')])
    bones=[dict(name=part+'_'+side) for side in ('l','r') for part in ('upperarm','forearm','hand')]
    attachments={}
    for offset,side in ((0,'l'),(3,'r')):
        vertices=[3]
        for i in range(3):vertices.extend([offset+i,0,0,1/3])
        key='arms-'+side
        attachments[key]={key:dict(type='mesh',uvs=[0,0],vertices=vertices)}
    files={'skeleton.json':canonical_bytes(dict(bones=bones,skins=[dict(attachments=attachments)]))}
    job=dict(project_id='p',job_id='j',artifact_sha256='a'*64,status='needs_review',layers=[layer],
             runtime=dict(geometry_status='passed',geometry_failed_records=0,frames=3))
    return job,files


class BilateralDefaultsTests(unittest.TestCase):
    def test_new_profile_accepts_only_new_jobs_and_legacy_replays_exactly(self):
        job,files=fixture()
        legacy=evaluate(job,files,profile=LEGACY_PROFILE)
        current=evaluate(job,files)
        self.assertEqual(legacy['accepted_layer_ids'],[])
        self.assertEqual(current['accepted_layer_ids'],['arms'])
        self.assertEqual(current['policy_id'],PROFILE)
        with TemporaryDirectory() as folder:
            root=Path(folder);original=canonical_bytes(legacy)
            (root/'stage-defaults.json').write_bytes(original)
            self.assertEqual(read(root,job,files),legacy)
            self.assertEqual((root/'stage-defaults.json').read_bytes(),original)
        self.assertEqual(evaluate(job,files,{'arms'})['accepted_layer_ids'],[])

    def test_opposite_side_or_unrelated_bone_is_rejected(self):
        job,files=fixture()
        for replacement in ('hand_r','chest'):
            doc=json.loads(files['skeleton.json']);doc['bones'][2]['name']=replacement
            if replacement=='hand_r':doc['bones'][5]['name']='unused'
            self.assertEqual(evaluate(job,{'skeleton.json':canonical_bytes(doc)})['accepted_layer_ids'],[])

    def test_incomplete_partition_and_runtime_failures_remain_exceptions(self):
        job,files=fixture()
        for change in ('missing','partial','one_side','failed'):
            value=deepcopy(job)
            if change=='missing':value['layers'][0]['missing_region_ids']=['residual']
            if change=='partial':value['layers'][0]['state']='partial'
            if change=='one_side':value['layers'][0]['regions'].pop()
            if change=='failed':value['runtime']['geometry_failed_records']=1
            self.assertEqual(evaluate(value,files)['accepted_layer_ids'],[])

    def test_unknown_profile_rejected(self):
        job,files=fixture()
        with self.assertRaisesRegex(ValueError,'profile_unknown'):evaluate(job,files,profile='future')
