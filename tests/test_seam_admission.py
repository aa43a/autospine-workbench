from copy import deepcopy
import unittest
from autospine_workbench.targets.spine43.seam_admission import evaluate


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        direct={'relations':[{'driver':'a','follower':'b','samples':[{'frame':1,'world_point':[1.5,2.5]}]}]}
        runtime={'schema':'autospine.seam-local-runtime/v2','capture_matrix':{'scales':[1],'atlases':['shared'],'modes':['pair','all']},'captures':[],'regression':[]}
        for variant in ('before','after'):
            runtime['regression'].append(dict(variant=variant,frames=[{'channels_over_one':0,'visible_pixels':1} for _ in range(121)],max_motion_error_px=0,max_setup_error_px=0,max_page_uv_error=0,outside_viewport_coordinates=0,animation_changed=True))
            for mode in ('pair','all'):
                runtime['captures'].append(dict(sample_index=0,variant=variant,scale=1,atlas='shared',mode=mode,point=[1.5,2.5],time=1/30,names=['a','b'],rgba=[[0,0,0,30 if variant=='before' else 6]]))
        geometry={'regions':{n:{'passed':True} for n in ('a','b')}}
        alpha={'relations':[{'driver':'a','follower':'b','max_distance_growth_px':1.9}]}
        return direct,runtime,geometry,alpha

    def test_loss_requires_review_without_authority(self):
        result=evaluate(*self.fixture());self.assertEqual(result['relations'][0]['status'],'review_runtime_alpha_loss')
        self.assertEqual(result['relations'][0]['new_all_alpha_below8'],1)
        self.assertFalse(result['production_authorized'])

    def test_restored_capture_is_only_sampled_pass(self):
        args=self.fixture()
        for c in args[1]['captures']:c['rgba'][0][3]=30
        self.assertEqual(evaluate(*args)['relations'][0]['status'],'sampled_no_new_regression')
        args[3]['relations'][0]['max_distance_growth_px']=2.1
        self.assertEqual(evaluate(*args)['relations'][0]['status'],'blocked_boundary_distance')

    def test_missing_duplicate_and_mismatched_identity_rejected(self):
        args=self.fixture();args[1]['captures'].pop()
        with self.assertRaises(ValueError):evaluate(*args)
        args=self.fixture();args[1]['captures'].append(deepcopy(args[1]['captures'][0]))
        with self.assertRaises(ValueError):evaluate(*args)
        args=self.fixture();args[1]['captures'][0]['point']=[0,0]
        with self.assertRaises(ValueError):evaluate(*args)

    def test_runtime_failure_not_hidden_by_good_geometry(self):
        args=self.fixture();args[1]['regression'][0]['max_motion_error_px']=1
        with self.assertRaises(ValueError):evaluate(*args)

    def test_empty_relation_not_counted_as_pass(self):
        args=self.fixture();args[0]['relations'][0]['samples']=[];args[1]['captures']=[]
        self.assertEqual(evaluate(*args)['relations'][0]['status'],'not_evaluated')
