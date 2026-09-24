from hashlib import sha256
import json
import unittest
from test_active_mesh_pose import ActiveMeshPoseTests
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deformation_qa import inspect


class ActiveDeformationQATests(unittest.TestCase):
    def fixtures(self, document=None):
        doc,report=ActiveMeshPoseTests().fixture()
        if document is not None:doc=document
        raw=json.dumps(doc).encode()
        frames=[]
        for time in (0.,.5,1.,1.5,2.):
            frame=sample_active(doc,'move',time)
            frames.append(dict(time=time,attachments=frame['attachments'],vertices=frame['vertices']))
        reference=dict(skeleton_sha256=sha256(raw).hexdigest(),animations={'move':frames})
        return doc,report,dict({'skeleton.json':raw,'numeric-reference.json':json.dumps(reference).encode()}),reference

    def test_main_entry_checks_distinct_topologies(self):
        _,report,files,_=self.fixtures();qa=inspect(files)
        self.assertEqual({r['attachment'] for r in qa['records']},{'leg',report['variant_attachment']})
        self.assertEqual(sum(r['sample_count'] for r in qa['records']),5)
        self.assertEqual(qa['transition_status'],'not_evaluated')

    def test_stale_identity_rejected_even_with_valid_vertices(self):
        _,_,files,ref=self.fixtures()
        ref['animations']['move'][1]['attachments']['leg']='leg'
        files['numeric-reference.json']=json.dumps(ref).encode()
        with self.assertRaisesRegex(ValueError,'active_attachment_mismatch'):inspect(files)

    def test_variant_failure_not_hidden_by_setup_mesh(self):
        doc,report,_,_=self.fixtures()
        doc['animations']['move']['attachments']['default']['leg'][report['variant_attachment']]['deform']=[
            dict(time=1,offset=17,vertices=[-20,0,-20,0,-20])]
        _,_,files,_=self.fixtures(doc);qa=inspect(files)
        row=next(r for r in qa['records'] if r['attachment']==report['variant_attachment'])
        self.assertFalse(qa['passed']);self.assertGreater(row['inversion_samples'],0)
        self.assertEqual(row['first_failure']['time'],1.)
