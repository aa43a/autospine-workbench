from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from PIL import Image
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_region_scene import build as scene
from autospine_workbench.targets.character43.material_region_candidate import build


def fixture():
    mesh=dict(type='mesh',uvs=[0,0,1,0,0,1,1,1],triangles=[0,1,2,1,3,2],vertices=[1,0,0,0,1,1,0,10,0,1,1,0,0,10,1,1,0,10,10,1])
    doc=dict(bones=[dict(name='root',rotation=0,x=0,y=0)],slots=[dict(name='arm',bone='root',attachment='arm')],
        skins=[dict(name='default',attachments={'arm':{'arm':mesh}})],
        animations={'reach':dict(bones={'root':{'rotate':[dict(time=0,value=0),dict(time=3,value=30)]}})})
    mapping=dict(mesh_sha256=canonical_sha256(mesh),triangles=[0],interval=[1,2],uv_policy='same_canvas_original_uv',
        geometry_policy='preserve_original_weights_and_deform',activation_policy='start_inclusive_end_exclusive_not_blend_or_visual_acceptance')
    plan=dict(slot='arm',animation='reach',mapping=mapping,draft_sha256='d'*64,artifact_sha256='a'*64)
    return doc,plan


class MaterialRegionTests(unittest.TestCase):
    def test_second_region_preserves_previous_switch_and_corrective(self):
        doc,plan=fixture()
        mesh=deepcopy(doc['skins'][0]['attachments']['arm']['arm'])
        doc['slots'].append(dict(name='leg',bone='root',attachment='leg'))
        doc['skins'][0]['attachments']['leg']={'leg':mesh}
        deform={'deform':[dict(time=0,vertices=[0]*8),dict(time=3,vertices=[1]*8)]}
        doc['animations']['reach']['attachments']={'default':{'leg':{'leg':deform}}}
        first,_=scene(doc,plan,'first-image')
        next_plan=deepcopy(plan);next_plan['slot']='leg'
        second,_=scene(first,next_plan,'second-image')
        for slot in first['slots']:
            if slot['name']=='leg':continue
            self.assertIn(slot,second['slots'])
            self.assertEqual(second['skins'][0]['attachments'][slot['name']],first['skins'][0]['attachments'][slot['name']])
        for slot,track in first['animations']['reach']['slots'].items():
            self.assertEqual(second['animations']['reach']['slots'][slot],track)
        self.assertEqual(second['animations']['reach']['attachments']['default']['leg-material-replacement']['leg-material-replacement'],deform)

    def test_complementary_switches_preserve_motion_and_disjoint_regions(self):
        doc,plan=fixture();original=deepcopy(doc);result,report=scene(doc,plan,'new-art')
        self.assertEqual(doc,original);self.assertEqual(result['bones'],doc['bones'])
        self.assertEqual(result['animations']['reach']['bones'],doc['animations']['reach']['bones'])
        meshes=result['skins'][0]['attachments'];self.assertEqual(meshes['arm']['arm']['triangles'],[1,3,2])
        a,b=report['original_region_slot'],report['replacement_slot']
        self.assertEqual(meshes[a][a]['triangles'],[0,1,2]);self.assertEqual(meshes[b][b]['vertices'],doc['skins'][0]['attachments']['arm']['arm']['vertices'])
        tracks=result['animations']['reach']['slots']
        self.assertEqual([k['value'] for k in tracks[a]['alpha']],[1,0,1])
        self.assertEqual([k['value'] for k in tracks[b]['alpha']],[0,1,0])
        self.assertTrue(all(k['curve']=='stepped' for k in tracks[b]['alpha']))
        for t in (0,.9999,1,1.5,2,3):
            points=sample(result,'reach',t)[0];expected=sample(doc,'reach',t)[0]['arm']
            self.assertTrue(all(p==expected for p in points.values()))

    def test_full_region_and_unsupported_tracks(self):
        doc,plan=fixture();plan['mapping']['triangles']=[0,1]
        result,report=scene(doc,plan,'new-art');self.assertEqual(report['added_slots'],['arm-material-replacement'])
        self.assertEqual(len(result['skins'][0]['attachments']['arm']['arm']['triangles']),6)
        doc['animations']['reach']['drawOrder']=[dict(time=1)]
        with self.assertRaisesRegex(ValueError,'existing_order'):scene(doc,plan,'new-art')

    def test_packaging_preserves_source_bytes_and_does_not_claim_repair(self):
        doc,plan=fixture();raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
        image=BytesIO();Image.new('RGBA',(2,2),'red').save(image,format='PNG');png=image.getvalue()
        request=dict(draft_sha256=plan['draft_sha256'],artifact_sha256=plan['artifact_sha256'],slot='arm',animation='reach',texture_size=[2,2])
        material={'request.json':canonical_bytes(request),'replacement.png':png}
        plan['material_bundle_sha256']=canonical_sha256({n:sha256(v).hexdigest() for n,v in material.items()})
        setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
        files={'skeleton.json':raw,'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest,vertices=setup)),
            'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,animations={'reach':[dict(time=0),dict(time=3)]})),
            'skeleton.atlas':b'old atlas\n','images/arm.png':png,'deformation.json':b'{"passed":false}',
            'motion-review.json':b'{"reference_length_px":10,"issues":[]}', 'character-manifest.json':b'{}',
            'motion-contact.json':b'{}','motion-ir.json':b'{}'}
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value=dict(status='unavailable_no_labels')):
            output,evidence,geometry=build(files,plan,material)
        self.assertEqual(output['images/arm.png'],png);self.assertTrue(geometry['passed'])
        self.assertEqual(evidence['status'],'needs_changes');self.assertNotIn('motion-depth.json',output)
        ref=json.loads(output['numeric-reference.json']);times=[f['time'] for f in ref['animations']['reach']]
        self.assertTrue(all(t in times for t in (1,2,.9999,1.0001,1.9999,2.0001)))
