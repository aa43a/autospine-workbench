from hashlib import sha256
from io import BytesIO
import unittest
from PIL import Image
from test_active_mesh_pose import ActiveMeshPoseTests
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.material_contact_trace import trace


class MaterialContactTraceTests(unittest.TestCase):
    def fixture(self):
        doc,report=ActiveMeshPoseTests().fixture()
        stream=BytesIO();Image.new('RGBA',(4,4),(255,255,255,255)).save(stream,format='PNG')
        path='images/leg.png';textures={path:stream.getvalue()}
        for mesh in doc['skins'][0]['attachments']['leg'].values():mesh['path']='leg'
        req=dict(document_sha256=canonical_sha256(doc),animation='move',interval=[0,2],
            times=[0,.5,1,1.5,2],limit_px=1,anchors=[dict(id='point',slot='leg',uv=[.2,.2],
            texture_path=path,texture_sha256=sha256(textures[path]).hexdigest())])
        return doc,textures,req,report

    def test_same_material_survives_topology_switch(self):
        doc,textures,req,report=self.fixture();result=trace(doc,textures,req)
        row=result['records'][0]
        self.assertEqual(row['unresolved_samples'],0)
        self.assertEqual(row['samples'][1]['attachment'],report['variant_attachment'])

    def test_material_moves_while_bone_timeline_unchanged(self):
        doc,textures,req,_=self.fixture()
        baseline=trace(doc,textures,req)['records'][0]['samples'][1]['world']
        motion=doc['animations']['move']
        motion['bones']={}
        # Restrict offsets to each attachment's influence count.
        from autospine_workbench.targets.character43.deform_addition import entries
        for name,mesh in doc['skins'][0]['attachments']['leg'].items():
            n=sum(map(len,entries(mesh)))
            motion['attachments']['default']['leg'][name]['deform']=[dict(time=0,vertices=[0,0]*n),dict(time=.5,vertices=[10,0]*n),dict(time=2,vertices=[10,0]*n)]
        req['document_sha256']=canonical_sha256(doc)
        result=trace(doc,textures,req)
        self.assertFalse(result['passed'])
        self.assertGreater(result['records'][0]['maximum_drift_px'],1)
        moved=result['records'][0]['samples'][1]['world']
        self.assertGreater(abs(moved[0]-baseline[0])+abs(moved[1]-baseline[1]),1)

    def test_hidden_start_cannot_rebase_to_later_visible_frame(self):
        doc,textures,req,_=self.fixture()
        doc['animations']['move']['slots']['leg']['attachment'][0]['name']=None
        req['document_sha256']=canonical_sha256(doc)
        result=trace(doc,textures,req)
        self.assertIsNone(result['passed'])
        self.assertEqual(result['records'][0]['samples'][1]['status'],'interval_origin_unresolved')

    def test_texture_identity_rejected(self):
        doc,textures,req,_=self.fixture();textures['images/leg.png']+=b'x'
        with self.assertRaisesRegex(ValueError,'texture_changed'):trace(doc,textures,req)

    def test_replacement_texture_requires_explicit_correspondence(self):
        doc,textures,req,report=self.fixture()
        doc['skins'][0]['attachments']['leg'][report['variant_attachment']]['path']='new-pose'
        req['document_sha256']=canonical_sha256(doc)
        result=trace(doc,textures,req)
        self.assertEqual(result['records'][0]['samples'][1]['status'],'material_correspondence_missing')
        self.assertNotEqual(result['passed'],True)

    def test_interval_cannot_extend_animation_by_holding_last_pose(self):
        doc,textures,req,_=self.fixture();req['interval'][1]=100;req['times'][-1]=100
        with self.assertRaisesRegex(ValueError,'outside_animation'):trace(doc,textures,req)
