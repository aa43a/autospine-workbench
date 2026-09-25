from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.motion_scope_order_parent import verify,PROFILE


class ScopeOrderParentTests(unittest.TestCase):
    def fixture(self):
        draft=dict(action='contact_scope',artifact_sha256='old')
        parent=dict(profile=PROFILE,draft=draft,draft_sha256=canonical_sha256(draft))
        mesh=dict(type='mesh',triangles=[0,1,2])
        row=dict(action='region_order',slot='region',region_order=dict(mesh_sha256=canonical_sha256(mesh)))
        files={'motion-repair-provenance.json':canonical_bytes(dict(parent,authority='none',selected=False)),
               'motion-repair.json':b'{"selected":false}',
               'skeleton.json':canonical_bytes(dict(skins=[dict(attachments={'region':{'region':mesh}})]))}
        return dict(repair_execution=parent),row,files

    def test_exact_scope_provenance_and_new_mesh_preserved(self):
        request,row,files=self.fixture();before=deepcopy(files)
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'current'},files)):
            result=verify(None,'parent',request,row,'current')
        self.assertEqual(result,sha256(files['motion-repair-provenance.json']).hexdigest())
        self.assertEqual(files,before)

    def test_stale_artifact_mesh_or_provenance_rejected(self):
        for change in ('artifact','mesh','provenance','missing'):
            request,row,files=self.fixture()
            artifact='changed' if change=='artifact' else 'current'
            if change=='mesh':row['region_order']['mesh_sha256']='stale'
            if change=='provenance':files['motion-repair-provenance.json']=b'{}'
            if change=='missing':files.pop('motion-repair-provenance.json')
            with self.subTest(change=change),patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':artifact},files)),self.assertRaises(RuntimeError):
                verify(None,'parent',request,row,'current')

    def test_other_nested_actions_stay_rejected(self):
        request,row,_=self.fixture();row['action']='local_repair'
        with self.assertRaisesRegex(RuntimeError,'nested'):verify(None,'parent',request,row,'current')
        self.assertIsNone(verify(None,'parent',{},row,'current'))


if __name__=='__main__':unittest.main()
