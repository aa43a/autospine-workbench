from base64 import b64decode
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from hashlib import sha256
import importlib.util
import json
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_component_plan import prepare
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.component_mount_candidate import generate


@unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
class ComponentCanvasTests(unittest.TestCase):
    def test_canvas_mapping_can_be_saved_without_client_hash_calculation(self):
        from PIL import Image,ImageDraw
        files=fixture(); image=Image.new('RGBA',(80,100));draw=ImageDraw.Draw(image)
        draw.rectangle((5,5,20,20),fill='white');draw.rectangle((50,65,70,85),fill='white')
        image.putpixel((40,40),(1,2,3,7));stream=BytesIO();image.save(stream,format='PNG');files['images/skirt.png']=stream.getvalue()
        manifest=json.loads(files['character-manifest.json'])
        for layer in manifest['layers']:
            for region in layer['regions']:region['state']=layer['state']
        files['character-manifest.json']=canonical_bytes(manifest)
        before=dict(files);digest=canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'request.json').write_bytes(b'{}')
            manager=SimpleNamespace(get=lambda *_:dict(status='needs_review',artifact_sha256=digest),
                verified_files=lambda *_:files,_path=lambda _:root,_current=lambda _:None)
            plan=prepare(manager,'project',dict(job_id='job',region_id='skirt'))
            from jsonschema import Draft202012Validator
            Draft202012Validator(json.loads((Path(__file__).parents[1]/'schemas/component-mount-canvas-v1.schema.json').read_bytes())).validate(plan)
            self.assertEqual(plan['residual_pixels'],1);self.assertEqual(len(plan['parts']),2)
            for part in plan['parts']:
                mask=Image.open(BytesIO(b64decode(part['mask'].split(',')[1])))
                self.assertEqual(sum(v>0 for v in mask.getchannel('A').tobytes()),part['visible_pixels'])
            decision=dict(schema='autospine.component-mount-decision/v1',source_bundle_sha256=digest,
                source_region_id='skirt',plan_sha256=plan['plan_sha256'],decision_source='human_confirmation',reversible=True,
                parents={p['component_id']:'chest' for p in plan['parts']})
            _,report=generate(files,'skirt',plan['allowed_parents'],decision)
            self.assertFalse(report['parent_review_required']);self.assertEqual(files,before)
            with self.assertRaisesRegex(RuntimeError,'unsupported'):prepare(manager,'project',dict(job_id='job',region_id='shirt'))
