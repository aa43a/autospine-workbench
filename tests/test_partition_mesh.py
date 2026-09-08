"""Regional weights stay within their side and expose raster/geometry failures."""
from copy import deepcopy
import math
import unittest
from PIL import Image,ImageDraw

from autospine_workbench.asset.joints.partition_pixels import png
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.partition_mesh_qa import raster_support,evaluate


def fixture():
    image=Image.new('RGBA',(24,80));ImageDraw.Draw(image).rectangle((7,3,16,76),fill=(100,140,200,255))
    raw=png('RGBA',image.size,image.tobytes());bones=[]
    points=[[112,200],[112,230],[112,260],[118,280]]
    for i,name in enumerate(('thigh_l','calf_l','foot_l')):
        a,b=points[i:i+2]
        bones.append({'id':name,'parent_id':bones[-1]['id'] if bones else 'pelvis','head_xy':a,'tail_xy':b,
                      'world_rotation_degrees':math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))})
    return raw,{'layer_id':'layer-001','bbox':[100,200,124,280]},'l',[b['id'] for b in bones],{'bones':bones}


class PartitionMeshTests(unittest.TestCase):
    def test_regional_mesh_setup_weight_normalization_and_named_probes(self):
        args=fixture();before=deepcopy(args);row=build_region(*args)
        self.assertEqual(args,before)
        self.assertGreater(len(row['vertices_xy']),0)
        self.assertLess(row['qa']['setup_max_error'],1e-7)
        self.assertLess(row['qa']['weight_sum_max_error'],1e-9)
        self.assertEqual(len(row['qa']['probes']),27)
        self.assertTrue(any(p['id']=='calf_l_+60' for p in row['qa']['probes']))
        self.assertTrue(any(p['id']=='foot_l_-30' for p in row['qa']['probes']))
        self.assertTrue(all(i['bone_id'].endswith('_l') for w in row['weights'] for i in w))
        self.assertEqual(row,build_region(*args))

    def test_single_foot_is_rigid_and_other_side_rejected(self):
        args=list(fixture());args[3]=['foot_l'];row=build_region(*args)
        self.assertTrue(row['qa']['passed'])
        self.assertTrue(all(w==1 for weights in row['weights'] for w in [weights[0]['weight']]))
        self.assertEqual(len(row['qa']['probes']),9)
        args[2]='r'
        with self.assertRaisesRegex(ValueError,'chain_invalid'):build_region(*args)

    def test_raster_support_detects_pixels_outside_mesh(self):
        vertices=[[0,0],[2,0],[2,4],[0,4]];triangles=[[0,1,2],[0,2,3]]
        qa=raster_support(bytes([255])*16,4,4,vertices,triangles,(0,0))
        self.assertEqual(qa['uncovered_alpha_pixels'],8)
        self.assertEqual(qa['uncovered_alpha_sum'],8*255)

    def test_qa_rejects_wrong_influence(self):
        args=fixture();row=build_region(*args);weights=deepcopy(row['weights'])
        with self.assertRaisesRegex(ValueError,'shape_invalid'):
            evaluate(row['vertices_xy'],row['triangles'],weights[:-1],args[-1]['bones'])
        weights[0][0]['bone_id']='thigh_r'
        with self.assertRaisesRegex(ValueError,'influence_invalid'):
            evaluate(row['vertices_xy'],row['triangles'],weights,args[-1]['bones'])
