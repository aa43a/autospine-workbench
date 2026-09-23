import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
from autospine_workbench.automation import motion_material_return as module
from autospine_workbench.automation.animated_store import AnimatedStore
import test_motion_repair_material as fixture_module


class ReturnTests(unittest.TestCase):
    def setUp(self):
        fixture=fixture_module.MaterialTests();fixture.setUp()
        from autospine_workbench.automation.motion_repair_material import build
        self.archive=build(fixture.report,fixture.row)
        with ZipFile(BytesIO(self.archive)) as archive:
            self.request=json.loads(archive.read('request.json'))
        self.png=fixture.png
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manager=SimpleNamespace(_lock=RLock(),folder=lambda _:Path(self.temp.name))
        self.mock=patch('autospine_workbench.automation.motion_repair_material.download',return_value=self.archive)
        self.download=self.mock.start();self.addCleanup(self.mock.stop)

    def body(self):
        return dict(request=dict(self.request),png_base64=base64.b64encode(self.png).decode())

    def test_immutable_idempotent_roundtrip(self):
        first=module.save(self.manager,'job',self.body())
        self.assertEqual(first,module.save(self.manager,'job',self.body()))
        restored=SimpleNamespace(_lock=RLock(),folder=self.manager.folder)
        self.assertEqual(module.inspect(restored,'job')['returns'],[first])
        files=AnimatedStore(Path(self.temp.name)/'material-returns').read(first['material_bundle_sha256'])
        self.assertEqual(files['replacement.png'],self.png)
        self.assertTrue(first['unchanged_source']);self.assertFalse(first['replacement_applied'])

    def test_cross_candidate_and_changed_request_rejected(self):
        for key,value in [('job_id','other'),('artifact_sha256','b'*64),('slot','other')]:
            body=self.body();body['request'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'identity_changed'):
                module.save(self.manager,'job',body)
        self.assertFalse((Path(self.temp.name)/'material-returns').exists())

    def test_withdrawal_checked_before_storage(self):
        self.download.side_effect=RuntimeError('motion_material_plan_superseded')
        with self.assertRaisesRegex(RuntimeError,'superseded'):module.save(self.manager,'job',self.body())
        self.assertFalse((Path(self.temp.name)/'material-returns').exists())

    def test_invalid_png_size_mode_and_truncation(self):
        cases=[b'not png',self.png[:30]]
        for mode,size in [('RGB',(40,30)),('RGBA',(41,30))]:
            output=BytesIO();Image.new(mode,size).save(output,format='PNG');cases.append(output.getvalue())
        for raw in cases:
            with self.subTest(size=len(raw)),self.assertRaisesRegex(RuntimeError,'png_invalid'):
                module.validate_png(base64.b64encode(raw).decode(),[40,30])

    def test_route(self):
        from autospine_workbench.automation.motion_intake_routes import _methods
        self.assertEqual(_methods(['job','material-return']),'GET, HEAD, POST, OPTIONS')
