from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_batch_player import run
from m4_experiment_player_export import export


class TransversePlayerTests(unittest.TestCase):
    def test_requires_complete_runtime_before_export(self):
        with patch('m4_transverse_batch_player.audit',return_value={'runtime_status':'not_evaluated'}), \
             patch('m4_transverse_batch_player.export') as writer:
            with self.assertRaisesRegex(ValueError,'runtime_required'):run(None,None,None)
            writer.assert_not_called()

    def test_viewport_covers_all_batches_without_granting_adoption(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);skeleton={'test':'same-curve'}
            rows=[dict(folder=f'batch-{i:03d}',candidate_bundle_sha256='candidate') for i in range(2)]
            (root/'report.json').write_bytes(canonical_bytes(dict(rows=rows,skeleton_sha256=sha256(canonical_bytes(skeleton)).hexdigest())))
            for i,row in enumerate(rows):
                folder=root/row['folder']/'runtime';folder.mkdir(parents=True)
                (folder/'report.json').write_bytes(canonical_bytes(dict(info=dict(left=-i,bottom=-i,width=4+i,height=5+i))))
            def writer(folder,**kwargs):
                self.assertEqual(kwargs['candidate_bundle_sha256'],'candidate')
                assets=folder/'runtime/player-assets';assets.mkdir()
                (assets/'scene.json').write_bytes(canonical_bytes(dict(skeleton=skeleton,info={})))
            with patch('m4_transverse_batch_player.audit',return_value=dict(runtime_status='passed',geometry_passed=False)), \
                 patch('m4_transverse_batch_player.export',side_effect=writer):
                report=run(None,None,root)
            self.assertEqual(report['viewport'],dict(left=-1,bottom=-1,width=5,height=6))
            self.assertFalse(report['selected']);self.assertFalse(report['coverage']['geometry_passed'])
            self.assertEqual(report['pending_checks'],['contact','depth','visual'])

    def test_explicit_bundle_does_not_skip_capture_identity_check(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);(root/'runtime').mkdir()
            (root/'runtime/report.json').write_text(json.dumps(dict(bundle_sha256='other',passed=True)))
            with self.assertRaisesRegex(ValueError,'capture_mismatch'):export(root,candidate_bundle_sha256='candidate')
