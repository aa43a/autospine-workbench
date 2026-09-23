import base64
import copy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from autospine_workbench.automation import motion_repair_material as material
from autospine_workbench.resolved_project import canonical_sha256


class MaterialTests(unittest.TestCase):
    def setUp(self):
        image=BytesIO(); Image.new('RGBA',(40,30),(255,0,0,255)).save(image,format='PNG')
        self.png=image.getvalue()
        self.event=dict(triangle=2,time=0.25,texture_uv=[[0,0],[1,0],[0,1]],sampled_world=[[10,20],[30,20],[10,50]])
        self.report=dict(artifact_sha256='a'*64,rows=[dict(slot='arm',animation='wave',details=[self.event],
            texture='data:image/png;base64,'+base64.b64encode(self.png).decode())])
        stripped=copy.deepcopy(self.report);del stripped['rows'][0]['texture']
        self.row=dict(artifact_sha256='a'*64,evidence_sha256=canonical_sha256(stripped),
            slot='arm',animation='wave',event=self.event,action='pose_attachment',notes='<script>note</script>',
            revision=1,job_id='job')

    def test_exact_bytes_inventory_and_coordinate_conversion(self):
        raw=material.build(self.report,self.row)
        self.assertEqual(raw,material.build(self.report,self.row))
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.read('source-texture.png'),self.png)
            inventory=json.loads(archive.read('inventory.json'))
            for name,digest in inventory.items():self.assertEqual(sha256(archive.read(name)).hexdigest(),digest)
            request=json.loads(archive.read('request.json'))
            self.assertEqual(request['source_pixel_triangle'],[[0,0],[40,0],[0,30]])
            self.assertFalse(request['missing_art_proven'])
            self.assertIn(b'10,-20',archive.read('deformed-triangle.svg'))
            self.assertNotIn(b'<script>',archive.read('source-location.svg'))
            self.assertEqual(request['draft_sha256'],canonical_sha256(self.row))

    def test_stale_and_non_material_plan_rejected(self):
        for key,value in [('artifact_sha256','b'*64),('evidence_sha256','c'*64),('action','withdraw'),('action','local_repair')]:
            row={**self.row,key:value}
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):material.build(self.report,row)

    def test_preview_is_in_inventory_without_changing_return_contract(self):
        with ZipFile(BytesIO(material.build(self.report,self.row,preview=b'<html>context</html>'))) as archive:
            inventory=json.loads(archive.read('inventory.json'))
            self.assertEqual(inventory['pose-preview.html'],sha256(b'<html>context</html>').hexdigest())
            request=archive.read('request.json')
        with ZipFile(BytesIO(material.build(self.report,self.row))) as archive:
            self.assertEqual(request,archive.read('request.json'))

    def test_revoked_and_superseded_download_rejected(self):
        newer={**self.row,'revision':2,'action':'withdraw'}
        with patch('autospine_workbench.automation.motion_repair_draft.history',return_value=[self.row,newer]), \
             patch('autospine_workbench.automation.motion_target_jobs.review_file',return_value=(json.dumps(self.report).encode(),'application/json')):
            from threading import RLock
            from types import SimpleNamespace
            with self.assertRaisesRegex(RuntimeError,'superseded'):
                material.download(SimpleNamespace(_lock=RLock()),'job','1')

    def test_route_is_readonly(self):
        from autospine_workbench.automation.motion_intake_routes import _methods
        self.assertEqual(_methods(['job','repair-material','1']),'GET, HEAD, OPTIONS')
