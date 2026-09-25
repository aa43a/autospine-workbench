import json
import unittest
from copy import deepcopy
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

    def test_other_attachment_failures_and_all_its_frames_remain_visible(self):
        files, variant, _, _ = self.fixture()
        doc = json.loads(files['skeleton.json'])
        other = deepcopy(doc['slots'][0])
        other.update(name='other', attachment='other')
        doc['slots'].append(other)
        mesh = deepcopy(doc['skins'][0]['attachments']['leg']['leg'])
        doc['skins'][0]['attachments']['other'] = {'other': mesh}
        doc['animations']['move']['attachments']['default']['other'] = {
            'other': {'deform': [dict(time=0, vertices=[0, 0, 100, 0])]}}
        _, _, changed, reference = ActiveDeformationQATests().fixtures(doc)
        for slot, choices in doc['skins'][0]['attachments'].items():
            for name, attachment in choices.items():
                changed['images/'+attachment.get('path', name)+'.png'] = b'png'
        changed['deformation.json'] = json.dumps(inspect(changed)).encode()
        before = deepcopy(changed)
        rows = build(changed, 'a'*64)['rows']
        self.assertTrue(any(r['attachment'] == variant['variant_attachment'] for r in rows))
        row = next(r for r in rows if r['slot'] == 'other')
        self.assertEqual(row['sample_count'], len(reference['animations']['move']))
        self.assertGreater(row['failed_area_triangles'], 0)
        self.assertEqual(changed, before)
