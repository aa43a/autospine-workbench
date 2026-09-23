import json
from pathlib import Path
from unittest import TestCase
from autospine_workbench.automation.motion_material_preview import build


class MaterialPreviewTests(TestCase):
    def test_embeds_verified_scene_and_removes_external_assets(self):
        web=Path(__file__).resolve().parents[1]/'web'
        row=dict(artifact_sha256='a'*64,animation='wave',slot='arm',event=dict(time=.5,triangle=3))
        scene=dict(artifact_sha256='a'*64,skeleton=dict(animations={'wave':{}},slots=[dict(name='arm')]))
        def read(parts):
            name=parts[-1]
            if name=='scene.json':return json.dumps(scene).encode(),''
            if name=='runtime.js':return b'window.spine={};',''
            path={'player.html':'character-player.html','client.js':'character-player.js',
                  'inspection.js':'character-player-inspection.js','style.css':'character-player.css'}[name]
            return (web/path).read_bytes(),''
        result=build(read,row)
        self.assertNotIn(b'src="player-assets/',result)
        self.assertNotIn(b'href="report.json"',result)
        self.assertIn(b'inspectTriangle(event.slot',result)
        self.assertIn(b'"time": 0.5',result)
        scene['artifact_sha256']='b'*64
        with self.assertRaisesRegex(RuntimeError,'identity_changed'):build(read,row)
        scene['artifact_sha256']='a'*64;row['slot']='wrong'
        with self.assertRaisesRegex(RuntimeError,'event_invalid'):build(read,row)
