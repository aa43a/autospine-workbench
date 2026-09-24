import json
import unittest
from test_active_deformation_qa import ActiveDeformationQATests
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.motion_geometry_details import build


class ActiveGeometryDetailsTests(unittest.TestCase):
    def fixture(self):
        helper=ActiveDeformationQATests();doc,report,_,_=helper.fixtures()
        doc['animations']['move']['attachments']['default']['leg'][report['variant_attachment']]['deform']=[
            dict(time=1,offset=17,vertices=[-20,0,-20,0,-20])]
        _,_,files,ref=helper.fixtures(doc)
        mesh=doc['skins'][0]['attachments']['leg'][report['variant_attachment']]
        files['images/'+mesh.get('path','leg')+'.png']=b'png'
        files['deformation.json']=json.dumps(inspect(files)).encode()
        return files,report,mesh,ref

    def test_actual_variant_triangle_uv_and_time_without_legacy_setup(self):
        files,variant,mesh,_=self.fixture();before=dict(files)
        result=build(files,'a'*64)
        row=next(r for r in result['rows'] if r['attachment']==variant['variant_attachment'])
        self.assertEqual(row['repair_scope'],'active_attachment_read_only')
        self.assertEqual(row['sample_count'],2)
        for detail in row['details']:
            self.assertEqual(detail['time'],1.)
            tri=mesh['triangles'][3*detail['triangle']:3*detail['triangle']+3]
            self.assertEqual(detail['texture_uv'],[mesh['uvs'][2*v:2*v+2] for v in tri])
        self.assertEqual(files,before)

    def test_mismatched_active_identity_cannot_localize(self):
        files,_,_,ref=self.fixture()
        ref['animations']['move'][1]['attachments']['leg']='leg'
        files['numeric-reference.json']=json.dumps(ref).encode()
        with self.assertRaisesRegex(ValueError,'active_attachment_mismatch'):
            build(files,'a'*64)
