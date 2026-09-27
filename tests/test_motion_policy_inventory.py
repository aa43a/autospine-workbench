import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_policy_inventory import inspect


class PolicyInventoryTests(unittest.TestCase):
    def test_policy_variant_keeps_source_character_and_clip_identity(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            requests = {'base': {}, 'view': {'projection': {'yaw_degrees': 30}},
                        'moving': {'moving_ankle_profile': 'moving-v1', 'contact_correction': False},
                        'other-rig': {'character_sha256': 'other', 'pose_profile': 'new'},
                        'other-clip': {'clip': {'start_frame': 3}, 'pose_profile': 'new'},
                        'other-source': {'source_job_id': 'foreign', 'pose_profile': 'new'}}
            for key, changes in requests.items():
                key = 'motion-' + key
                folder = root / key; folder.mkdir()
                (folder/'request.json').write_bytes(canonical_bytes(dict(
                    dict(kind='adapt', job_id=key, source_job_id='source', project_id='project',
                         character_job_id='character', character_sha256='rig', contact_correction=True), **changes)))
            def get(job):
                if job in ('source', 'foreign'):
                    return dict(source_sha256=job, format='fbx', view='front')
                return dict(status='succeeded')
            manager = SimpleNamespace(root=root, folder=lambda job:root/job, get=get)
            with patch('autospine_workbench.automation.motion_policy_inventory.stage_review',
                       return_value=dict(artifact_sha256='artifact', evidence_sha256='evidence')):
                report = inspect(manager, 'motion-base')
            self.assertEqual([r['job_id'] for r in report['rows']], ['motion-moving'])
            self.assertTrue(report['complete'])
            self.assertIsNone(report['recommended_job_id'])
            self.assertEqual(report['rows'][0]['policy_changes']['contact_correction'],
                             dict(baseline=True, candidate=False))
