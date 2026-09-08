"""Target-coordinate and flattened influence timeline checks, not official Runtime."""
import math
import unittest
from copy import deepcopy
from tests import test_elbow_constraints
from autospine_workbench.asset.joints.elbow_bake import build_bake,replay
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.spine43.elbow_preview import build_preview
from autospine_workbench.benchmark.elbow_target_cli import archive


class ElbowTargetTests(unittest.TestCase):
    def setUp(self):
        f=test_elbow_constraints.ElbowConstraintsTests();f.setUp()
        self.bones=f.bones
        for b in self.bones:
            b['setup_local']={'x':b['head_xy'][0] if b['id']=='upperarm' else 10,'y':0,'rotation_degrees':0}
            b['length']=10
        self.bones[0]['parent_id']=None
        row=f.row;row['uvs']=[[p[0]/30,p[1]/10] for p in row['vertices_xy']]
        self.candidate={'canvas':[30,10],'layers':[{'layer_id':'arm','bbox':[0,0,30,10]}]}
        self.skeleton={'bones':self.bones,'candidate_sha256':canonical_sha256(self.candidate)}
        self.mesh={'profile':'joint-plane-three-bone-v2','layers':[row]}
        self.bake=build_bake(self.mesh,self.skeleton)

    def test_target_encoding_reconstructs_key_and_between_keys(self):
        doc,scope=build_preview(self.mesh,self.skeleton,self.bake,self.candidate)
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'schemas/elbow-target-preview-v1.schema.json').read_text('utf-8'))).validate(scope)
        self.assertEqual(scope['scope'],'selected_mesh_layers_only')
        self.assertEqual(scope['full_character_status'],'blocked')
        animation=doc['animations']['elbow-diagnostic']
        self.assertNotIn('deform',animation)
        keys=animation['attachments']['default']['arm']['arm']['deform']
        vertices=doc['skins'][0]['attachments']['arm']['arm']['vertices']
        for frame,t in ((0,0),(14,.5),(15,0),(44,.25),(59,1)):
            angle=animation['bones']['forearm']['rotate'][frame]['value']*(1-t)+animation['bones']['forearm']['rotate'][frame+1]['value']*t
            radians=math.radians(angle);cos,sin=math.cos(radians),math.sin(radians)
            frames=[([0,0],0),([10,0],angle),([10+10*cos,10*sin],angle)]
            offsets=[a+(b-a)*t for a,b in zip(keys[frame]['vertices'],keys[frame+1]['vertices'])]
            points=[];index=0;offset=0
            while index<len(vertices):
                count=vertices[index];index+=1;x=y=0
                for _ in range(count):
                    bone,lx,ly,w=vertices[index:index+4];index+=4
                    lx+=offsets[offset];ly+=offsets[offset+1];offset+=2
                    head,rotation=frames[bone];r=math.radians(rotation)
                    x+=w*(head[0]+lx*math.cos(r)-ly*math.sin(r));y+=w*(head[1]+lx*math.sin(r)+ly*math.cos(r))
                points.append([x,-y])
            frames_src=self.bake['layers'][0]['frames']
            expected=replay(self.mesh['layers'][0],self.bones,frames_src[frame],frames_src[frame+1],t)
            for p,q in zip(points,expected):self.assertLess(math.dist(p,q),1e-10)

    def test_wrong_candidate_and_failed_bake_refused(self):
        bad=deepcopy(self.candidate);bad['canvas'][0]+=1
        with self.assertRaisesRegex(ValueError,'elbow_preview_source_mismatch'):build_preview(self.mesh,self.skeleton,self.bake,bad)
        self.bake['layers'][0]['status']='passed';self.bake['layers'][0]['qa']['min_area_ratio']=9
        with self.assertRaisesRegex(ValueError,'elbow_bake_mismatch'):build_preview(self.mesh,self.skeleton,self.bake,self.candidate)

    def test_archive_reproducible(self):
        self.assertEqual(archive({'a':b'one','b':b'two'}),archive({'b':b'two','a':b'one'}))

    def test_no_selected_mesh_is_blocked(self):
        self.mesh['layers'][0]['weights']=[]
        bake=build_bake(self.mesh,self.skeleton)
        with self.assertRaisesRegex(ValueError,'elbow_preview_mesh_required'):
            build_preview(self.mesh,self.skeleton,bake,self.candidate)
