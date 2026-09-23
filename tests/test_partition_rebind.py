from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.partition_rebind import apply


def fixture():
    mesh=dict(type='mesh',uvs=[0,0,1,0,0,1,1,1],triangles=[0,1,2,1,3,2],
        vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1,1,0,1,1,1])
    doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0),dict(name='hand',parent='root',x=10,y=0,rotation=0)],
        slots=[dict(name='mesh',bone='root',attachment='mesh')],skins=[dict(name='default',attachments={'mesh':{'mesh':mesh}})],
        animations={'walk':{'bones':{'hand':{'rotate':[dict(time=0,value=0),dict(time=1,value=90)]}}}})
    plan=dict(slot='mesh',animation='walk',partition=dict(mesh_sha256=canonical_sha256(mesh),triangles=[0],bone='hand'))
    return doc,plan


class RebindTests(unittest.TestCase):
    def test_setup_texture_and_unselected_preserved_boundary_separates(self):
        doc,plan=fixture();before=deepcopy(doc);setup=sample(doc,'walk',0)[0]['mesh']
        result,rest,report=apply(doc,plan,setup)
        self.assertEqual(doc,before);self.assertEqual(result['bones'],doc['bones'])
        self.assertEqual(result['animations'],doc['animations'])
        self.assertEqual(sample(result,'walk',0)[0]['mesh'],rest)
        self.assertEqual(report['boundary_pairs'],[[1,5],[2,6]])
        posed=sample(result,'walk',1)[0]['mesh']
        self.assertEqual(posed[:4],sample(doc,'walk',1)[0]['mesh'])
        self.assertNotEqual(posed[1],posed[5])
        self.assertEqual(result['skins'][0]['attachments']['mesh']['mesh']['uvs'][-6:],[0,0,1,0,0,1])

    def test_original_deform_values_preserved_new_region_independent(self):
        doc,plan=fixture();doc['animations']['walk']['attachments']={'default':{'mesh':{'mesh':{'deform':[
            dict(time=0,offset=2,vertices=[.2,.3]),dict(time=1,offset=2,vertices=[.4,.5])]}}}}
        restdoc=deepcopy(doc);restdoc['animations']={'walk':{}}
        setup=sample(restdoc,'walk',0)[0]['mesh'];result,_,_=apply(doc,plan,setup)
        doc['animations']['walk']['attachments']['default']['mesh']['mesh']['deform']=[
            dict(time=0,vertices=[0,0,.2,.3,0,0,0,0]),dict(time=1,vertices=[0,0,.4,.5,0,0,0,0])]
        for time in (0,.5,1):
            self.assertEqual(sample(result,'walk',time)[0]['mesh'][:4],sample(doc,'walk',time)[0]['mesh'])

    def test_changed_mesh_and_bad_selection_rejected(self):
        for change in ('identity','indices'):
            doc,plan=fixture();setup=sample(doc,'walk',0)[0]['mesh']
            if change=='identity':plan['partition']['mesh_sha256']='bad'
            else:plan['partition']['triangles']=[99]
            with self.assertRaises(ValueError):apply(doc,plan,setup)

    def test_build_retains_boundary_failure_without_acceptance(self):
        from autospine_workbench.targets.character43.partition_candidate import build
        doc,plan=fixture();raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
        setup=sample(doc,'walk',0)[0]
        files={'skeleton.json':raw,'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest,vertices=setup)),
            'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,animations={'walk':[dict(time=0),dict(time=1)]})),
            'motion-review.json':canonical_bytes(dict(reference_length_px=10,issues=[])),
            'motion-contact.json':b'{}','motion-ir.json':b'{}','character-manifest.json':b'{}',
            'deformation.json':b'{}','images/mesh.png':b'exact','skeleton.atlas':b'exact atlas'}
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'not_evaluated'}):
            output,evidence,_=build(files,plan)
        report=json.loads(output['motion-repair.json'])
        self.assertEqual(report['boundary']['failed_times'],1)
        self.assertEqual(evidence['status'],'needs_changes')
        self.assertEqual(output['images/mesh.png'],b'exact')
        self.assertEqual(output['skeleton.atlas'],b'exact atlas')
        self.assertFalse(report['selected'])
