"""Native alpha sampling distinguishes holes, overlap and transparent padding."""
import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_raster import mask,corridor,frame_probe
from autospine_workbench.targets.spine43.seam_conflicts import analyze
from tests.test_seam_translation import fixture


def quad():return {'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}


class SeamRasterTests(unittest.TestCase):
    def test_duplicate_correspondence_is_not_automatically_conflict(self):
        doc,_=fixture();s0={'triangle':[0,1,2],'barycentric':[1,0,0]};s1={'triangle':[0,1,2],'barycentric':[0,1,0]}
        report={'boundaries':{'leg':{'samples':[s0,s1]},'shoe':{'samples':[s0]}},'relations':[{'driver':'leg','follower':'shoe','pairs':[
            {'driver_sample':0,'follower_sample':0},{'driver_sample':1,'follower_sample':0}]}]}
        row=analyze(doc,report)[0]
        self.assertEqual(row['pair_count'],2);self.assertEqual(row['reciprocal_pair_count'],1)
        self.assertAlmostEqual(row['max_target_spread_px'],0);self.assertEqual(row['decision'],'retain_all_pending')
        keys=doc['animations']['continuous-corrective-inspection']['attachments']['default']['leg']['leg']['deform']
        keys[1]['vertices'][4]=8;keys[1]['vertices'][6]=8
        self.assertAlmostEqual(analyze(doc,report)[0]['max_target_spread_px'],4)
    def test_identity_texture_and_translation(self):
        alpha=np.array([[0,32],[128,255]],dtype=float)
        vertices=[[0,0],[2,0],[2,-2],[0,-2]]
        np.testing.assert_allclose(mask(quad(),vertices,alpha,[0,0,2,2]),alpha)
        shifted=[[x+5,y-3] for x,y in vertices]
        np.testing.assert_allclose(mask(quad(),shifted,alpha,[5,3,2,2]),alpha)

    def test_bilinear_sample_is_not_nearest_neighbor(self):
        vertices=[[0,0],[4,0],[4,-4],[0,-4]]
        result=mask(quad(),vertices,np.array([[0,255],[0,255]],dtype=float),[0,0,4,4])
        self.assertAlmostEqual(result[1,1],63.75);self.assertAlmostEqual(result[1,2],191.25)

    def test_corridor_clips_negative_coordinates(self):
        result=corridor([([-2,0],[2,0])],[0,0,3,1])
        self.assertEqual(result.tolist(),[[True,True,True]])

    def test_transparent_mesh_and_degenerate_triangle(self):
        vertices=[[0,0],[2,0],[2,-2],[0,-2]]
        self.assertFalse(mask(quad(),vertices,np.zeros((2,2)),[0,0,2,2]).any())
        q=quad();q['triangles']=[0,0,0]
        self.assertFalse(mask(q,vertices,np.ones((2,2))*255,[0,0,2,2]).any())

    def test_overlap_and_gap_counts(self):
        a=quad();a['vertices']=[v for x,y in ((0,0),(2,0),(2,-2),(0,-2)) for v in (1,0,x,y,1)]
        doc={'bones':[{'name':'root','x':0,'y':0,'rotation':0}],'skins':[{'attachments':{'a':{'a':a},'b':{'b':a}}}],'animations':{'test':{'bones':{}}}}
        sample={'triangle':[0,1,2],'barycentric':[.5,0,.5]};boundaries={'a':{'samples':[sample]},'b':{'samples':[sample]}}
        relation={'driver':'a','follower':'b','pairs':[{'driver_sample':0,'follower_sample':0}]}
        textures={'a':np.full((2,2),255.),'b':np.full((2,2),255.)}
        result,_=frame_probe(doc,relation,boundaries,textures,0)
        self.assertEqual(result['gap_pixels'],0);self.assertEqual(result['overlap_pixels'],1)
        result,_=frame_probe(doc,relation,boundaries,{n:np.zeros((2,2)) for n in textures},0)
        self.assertEqual(result['gap_pixels'],1);self.assertEqual(result['overlap_pixels'],0)
