import json
from io import BytesIO
from pathlib import Path
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from autospine_workbench.automation import motion_material_mapping as module
from autospine_workbench.resolved_project import canonical_sha256


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manager=SimpleNamespace(_lock=RLock(),folder=lambda _:Path(self.temp.name))
        self.mesh=dict(type='mesh',uvs=[0,0,1,0,0,1,1,1],triangles=[0,1,2,1,3,2])
        self.files={'skeleton.json':json.dumps(dict(bones=[],slots=[dict(name='arm')],skins=[dict(attachments={'arm':{'arm':self.mesh}})])).encode(),
            'numeric-reference.json':json.dumps(dict(animations={'reach':[dict(time=0),dict(time=4)]})).encode()}
        self.request=dict(draft_revision=1)
        self.receipt=dict(material_bundle_sha256='b'*64,artifact_sha256='a'*64,slot='arm',animation='reach',
            draft_revision=1,draft_sha256='c'*64,request_sha256=canonical_sha256(self.request))
        from autospine_workbench.automation.animated_store import AnimatedStore
        from autospine_workbench.automation.storage_io import canonical_bytes
        self.receipt['material_bundle_sha256']=AnimatedStore(Path(self.temp.name)/'material-returns').publish({'request.json':canonical_bytes(self.request)})
        stream=BytesIO()
        with ZipFile(stream,'w') as archive:archive.writestr('request.json',json.dumps(self.request))
        for target,value in [('motion_material_return.inspect',dict(returns=[self.receipt])),
            ('motion_repair_material.download',stream.getvalue()),
            ('motion_target_jobs.context',(dict(artifact_sha256='a'*64),self.files))]:
            mock=patch('autospine_workbench.automation.'+target,return_value=value)
            handle=mock.start();self.addCleanup(mock.stop)
            if target.endswith('download'):self.download=handle

    def body(self):
        return dict(expected_revision=0,action='map',material_bundle_sha256=self.receipt['material_bundle_sha256'],
            mesh_sha256=canonical_sha256(self.mesh),triangles=[1],interval=[1,3])

    def test_restore_and_withdraw_without_overwriting_candidate(self):
        original=dict(self.files);first=module.save(self.manager,'job',self.body())
        self.assertEqual(module.inspect(self.manager,'job'),first)
        result=module.save(self.manager,'job',dict(expected_revision=1,action='withdraw',material_bundle_sha256=self.receipt['material_bundle_sha256']))
        self.assertEqual([r['action'] for r in result['history']],['map','withdraw'])
        self.assertEqual(self.files,original)
        self.assertFalse(result['replacement_applied'])
        self.assertEqual(result['history'][1]['previous_sha256'],canonical_sha256(first['history'][0]))

    def test_mesh_region_interval_and_revision_rejected(self):
        for field,values in {'triangles':[[],[True],[2],[0,0]],'interval':[[0,5],[2,1],[0,float('nan')]],
            'mesh_sha256':['d'*64],'expected_revision':[1]}.items():
            for value in values:
                body=self.body();body[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(RuntimeError):module.save(self.manager,'job',body)
        self.assertEqual(module.inspect(self.manager,'job')['revision'],0)

    def test_superseded_artwork_plan_cannot_map(self):
        self.download.side_effect=RuntimeError('motion_material_plan_superseded')
        with self.assertRaisesRegex(RuntimeError,'superseded'):module.save(self.manager,'job',self.body())
        self.assertEqual(module.inspect(self.manager,'job')['revision'],0)

    def test_legacy_equal_numbers_keep_original_provenance(self):
        stream=BytesIO()
        with ZipFile(stream,'w') as archive:archive.writestr('request.json','{"draft_revision":1.0}')
        self.download.return_value=stream.getvalue()
        result=module.save(self.manager,'job',self.body())
        self.assertEqual(result['history'][0]['material_bundle_sha256'],self.receipt['material_bundle_sha256'])

    def test_tampered_history_rejected(self):
        module.save(self.manager,'job',self.body())
        path=Path(self.temp.name)/'material-mappings/mapping-0001.json'
        row=json.loads(path.read_bytes());row['previous_sha256']='bad'
        from autospine_workbench.automation.storage_io import canonical_bytes
        path.write_bytes(canonical_bytes(row))
        with self.assertRaisesRegex(RuntimeError,'history_invalid'):module.inspect(self.manager,'job')
