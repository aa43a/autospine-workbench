"""Alternative deformation retains setup and can reconstruct through local offsets."""
import math
import unittest
import json
from pathlib import Path
from copy import deepcopy
from tests.test_mesh_weights import chain
from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices
from autospine_workbench.asset.joints.mesh_weights import _deform,_frames
from autospine_workbench.asset.joints.elbow_alternatives import MODES,deform,corrective_offsets,validate_source
from autospine_workbench.asset.joints.elbow_comparison import build_comparison,validate_comparison


class ElbowComparisonTests(unittest.TestCase):
    def setUp(self):
        self.bones = chain()
        self.vertices = [[8,1],[9,1],[9,2]]
        self.weights = weights_for_vertices(self.vertices,self.bones)
        self.mesh = {'profile':'joint-plane-three-bone-v2','layers':[{'layer_id':'arm',
                     'vertices_xy':self.vertices,'weights':self.weights,'triangles':[[0,1,2]]}]}
        self.skeleton = {'bones':self.bones}

    def test_setup_identity_all_methods(self):
        for mode in MODES:
            for p,q in zip(self.vertices,deform(self.vertices,self.weights,self.bones,0,mode)):
                self.assertLess(math.dist(p,q),1e-12)

    def test_corrective_local_offsets_reconstruct_exactly(self):
        for angle in (-90,-30,0,30,90):
            offsets = corrective_offsets(self.vertices,self.weights,self.bones,angle)
            weights = deepcopy(self.weights)
            for row,deltas in zip(weights,offsets):
                for influence,delta in zip(row,deltas):
                    influence['local_xy'] = [v+d for v,d in zip(influence['local_xy'],delta)]
            replay = _deform(weights,_frames(self.bones,angle))
            target = deform(self.vertices,self.weights,self.bones,angle,'rotation_corrective')
            for p,q in zip(replay,target):self.assertLess(math.dist(p,q),1e-12)

    def test_rigid_endpoints_unchanged(self):
        vertices = [[0,1],[20,1],[25,2]]
        weights = weights_for_vertices(vertices,self.bones)
        baseline = deform(vertices,weights,self.bones,90,'lbs')
        for mode in MODES:
            for p,q in zip(baseline,deform(vertices,weights,self.bones,90,mode)):
                self.assertLess(math.dist(p,q),1e-12)

    def test_auxiliary_is_expressible_as_lbs_with_one_extra_bone(self):
        for angle in (-90,30,90):
            frames = _frames(self.bones,angle)
            frames['elbow_aux'] = (self.bones[1]['head_xy'],angle/2)
            lifted = []
            for vertex,row in zip(self.vertices,self.weights):
                t = row[1]['weight']+row[2]['weight']
                new = deepcopy(row)
                new[0]['weight'] = (1-t)**2
                for influence in new[1:]:influence['weight'] *= t
                new.append({'bone_id':'elbow_aux','weight':2*t*(1-t),
                            'local_xy':[vertex[0]-10,vertex[1]]})
                self.assertAlmostEqual(sum(i['weight'] for i in new),1)
                lifted.append(new)
            target = deform(self.vertices,self.weights,self.bones,angle,'half_angle_auxiliary')
            for p,q in zip(_deform(lifted,frames),target):self.assertLess(math.dist(p,q),1e-12)

    def test_deterministic_report_and_no_implicit_adoption(self):
        before = deepcopy((self.mesh,self.skeleton))
        doc = build_comparison(self.mesh,self.skeleton)
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[1]/'schemas/elbow-comparison-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)
        self.assertIsNone(doc['selected_method'])
        validate_comparison(self.mesh,self.skeleton,doc)
        self.assertEqual((self.mesh,self.skeleton),before)
        doc['layers'][0]['methods'][0]['min_area_ratio'] = 1
        with self.assertRaisesRegex(ValueError,'elbow_comparison_mismatch'):
            validate_comparison(self.mesh,self.skeleton,doc)

    def test_invalid_probe_and_wrong_weights_rejected(self):
        for angle in (True,math.nan,91,10**1000):
            with self.assertRaises(ValueError):deform(self.vertices,self.weights,self.bones,angle,'lbs')
        with self.assertRaises(ValueError):deform(self.vertices,self.weights,self.bones,0,'other')
        self.weights[0][0]['local_xy'][0] += 1
        with self.assertRaisesRegex(ValueError,'requires_joint_plane_weights'):
            validate_source(self.vertices,self.weights,self.bones)

    def test_no_mesh_is_not_evaluated(self):
        self.mesh['layers'][0]['weights'] = []
        self.assertEqual(build_comparison(self.mesh,self.skeleton)['layers'][0]['status'],'not_evaluated')
