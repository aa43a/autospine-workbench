"""Only explicit rigid choices join the scene; candidate contacts confer no authority."""
import hashlib
import io
import unittest
from copy import deepcopy
from tests import test_elbow_target
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.targets.spine43.character_preview import build_character
from autospine_workbench.asset.joints.character_contacts import contacts,locate
from autospine_workbench.asset.joints.elbow_bake import build_bake
from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices


class CharacterPreviewTests(unittest.TestCase):
    def setUp(self):
        f=test_elbow_target.ElbowTargetTests();f.setUp()
        self.mesh,self.skeleton,self.candidate=f.mesh,f.skeleton,f.candidate
        self.candidate['layers'] += [{'layer_id':'torso','bbox':[0,0,30,10]},{'layer_id':'pending','bbox':[0,0,1,1]}]
        self.skeleton['candidate_sha256']=canonical_sha256(self.candidate)
        self.bindings={'schema':'autospine.layer-binding-candidates/v2','authority':'none','production_authorized':False,
          'status':'needs_review','source_skeleton_sha256':canonical_sha256(self.skeleton),'candidate_sha256':canonical_sha256(self.candidate),
          'bindings':[{'layer_id':name,'status':'needs_review','options':options} for name,options in [
            ('arm',[{'id':'mesh','mode':'mesh_chain','bone_ids':['upperarm','forearm','hand']}]),
            ('torso',[{'id':'rigid','mode':'rigid','bone_ids':['upperarm'],'setup_local':{'x':15,'y':5,'rotation_degrees':0}}]),
            ('pending',[])]]}
        self.draft=build_layer_binding_draft(self.bindings)
        self.draft['records'][0].update(action='bind',option_id='mesh')
        self.draft['records'][1].update(action='bind',option_id='rigid')
        self.mesh.update(source_draft_sha256=canonical_sha256(self.draft),source_bindings_sha256=canonical_sha256(self.bindings))
        self.bake=build_bake(self.mesh,self.skeleton)

    def test_selected_regions_and_pending_separation(self):
        original=deepcopy(self.mesh)
        doc,scope=build_character(self.mesh,self.skeleton,self.bake,self.candidate,self.bindings,self.draft)
        self.assertEqual([s['name'] for s in doc['slots']],['arm','torso'])
        self.assertEqual(scope['rigid_layers'],['torso'])
        self.assertEqual(scope['excluded_layers'],[{'layer_id':'pending','reason_code':'binding_pending'}])
        region=doc['skins'][0]['attachments']['torso']['torso']
        self.assertEqual((region['x'],region['y'],region['rotation']),(15,-5,0))
        self.assertEqual(self.mesh,original)

    def test_changed_selection_cannot_reuse_mesh(self):
        self.draft['records'][1].update(action='pending',option_id=None)
        with self.assertRaisesRegex(ValueError,'character_preview_source_mismatch'):
            build_character(self.mesh,self.skeleton,self.bake,self.candidate,self.bindings,self.draft)

    def test_overlap_candidates_and_absence(self):
        from PIL import Image
        row=self.mesh['layers'][0];row['vertices_xy']=[[0,0],[4,0],[4,4]];row['triangles']=[[0,1,2]]
        row['weights']=weights_for_vertices(row['vertices_xy'],self.skeleton['bones'])
        self.bake=build_bake(self.mesh,self.skeleton)
        self.bindings['bindings'][1]['options'][0]['bone_ids']=['chest']
        for alpha in (255,0):
            stream=io.BytesIO();Image.new('RGBA',(30,10),(255,255,255,alpha)).save(stream,format='PNG');raw=stream.getvalue()
            for original in self.candidate['layers'][:2]:original['image_sha256']=hashlib.sha256(raw).hexdigest()
            report=contacts(self.candidate,self.mesh,self.skeleton,self.bake,self.bindings,self.draft,{'arm':raw,'torso':raw})
            pair=report['pairs'][0]
            self.assertFalse(report['seam_certified'])
            self.assertEqual(pair['status'],'candidate_requires_review' if alpha else 'unobservable')
            if alpha:self.assertAlmostEqual(pair['max_anchor_gap_px'],0)

    def test_barycentric_anchor_mapping(self):
        triangle,bary=locate([1,1],[[0,0],[4,0],[0,4]],[[0,1,2]])
        self.assertEqual(triangle,0);self.assertEqual(bary,[.5,.25,.25])
        self.assertIsNone(locate([5,5],[[0,0],[4,0],[0,4]],[[0,1,2]]))

    def test_scene_rejects_changed_bake(self):
        from autospine_workbench.benchmark.character_scene_view import render_scene
        doc,scope=build_character(self.mesh,self.skeleton,self.bake,self.candidate,self.bindings,self.draft)
        self.bake['layers'][0]['frames'][0]['angle']=12
        with self.assertRaisesRegex(ValueError,'elbow_bake_mismatch'):
            render_scene(self.candidate,self.skeleton,self.mesh,self.bake,doc,scope,{},b'')
