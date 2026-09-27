import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_regional_cloth_player import run


class ClothPlayerTests(unittest.TestCase):
    def test_incomplete_capture_cannot_create_player(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            with patch('m4_regional_cloth_player.audit',return_value={'complete':False}):
                with self.assertRaisesRegex(ValueError,'complete_runtime_required'):
                    run(root,root,root,root)
            self.assertEqual(list(root.iterdir()),[])

    def test_union_framing_and_failed_candidate_label(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);experiment=root/'experiment';experiment.mkdir()
            (experiment/'report.json').write_bytes(canonical_bytes(dict(frames=[dict(time=.9,uncovered=[1])])))
            skeleton={'animations':{}};digest=sha256(canonical_bytes(skeleton)).hexdigest()
            rows=[dict(folder=f'batch-{i:03d}',candidate_bundle_sha256='test') for i in range(2)]
            (root/'report.json').write_bytes(canonical_bytes(dict(rows=rows,skeleton_sha256=digest)))
            for i,row in enumerate(rows):
                folder=root/row['folder']/'runtime';folder.mkdir(parents=True)
                (folder/'report.json').write_bytes(canonical_bytes(dict(info=dict(left=i*10,bottom=0,width=20,height=30))))
            assets=root/'batch-000/runtime/player-assets';assets.mkdir()
            (assets/'scene.json').write_bytes(canonical_bytes(dict(artifact_sha256='test',skeleton=skeleton,info={})))
            with patch('m4_regional_cloth_player.audit',return_value=dict(complete=True,coverage=dict(frames=2))):
                run(root,experiment,root,root)
            scene=json.loads((assets/'scene.json').read_bytes())
            self.assertEqual(scene['info']['width'],30)
            report=json.loads((root/'player-report.json').read_bytes())
            self.assertFalse(report['selected'])
            self.assertEqual(report['coverage_failed_times'],1)
            self.assertIn('候选未采用',(root/'index.html').read_text(encoding='utf-8'))
