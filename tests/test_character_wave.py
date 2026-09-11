from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.wave_package import append_wave
from autospine_workbench.targets.character43.wave_motion import build_wave,pose


class WaveTests(unittest.TestCase):
    def fixture(self):
        bones=[dict(name='pelvis',x=0,y=0,rotation=0)]
        for name,parent,x,y,rotation in [('chest','pelvis',0,10,0),('clavicle_l','chest',0,0,0),
            ('upperarm_l','clavicle_l',5,0,-60),('forearm_l','upperarm_l',10,0,30),
            ('hand_l','forearm_l',10,0,0),('upperarm_r','chest',-5,0,0)]:
            bones.append(dict(name=name,parent=parent,x=x,y=y,rotation=rotation))
        return dict(bones=bones,animations={'old':{'bones':{}}})

    def test_preserve_setup_elbow_branch_and_reach_every_target(self):
        source=self.fixture();before=deepcopy(source);doc,evidence=build_wave(source)
        self.assertEqual(source,before);self.assertEqual(doc,build_wave(source)[0])
        for keys in doc['animations']['wave-left']['bones'].values():
            self.assertEqual(keys['rotate'][0]['value'],0);self.assertEqual(keys['rotate'][-1]['value'],0)
        self.assertTrue(all(k['endpoint_error_px']<1e-6 for k in evidence['ik_keys']))
        self.assertGreater(evidence['ik_keys'][1]['target'][1],pose(source['bones'])['hand_l'][1])

    def test_ambiguous_straight_elbow_and_wrong_hierarchy_rejected(self):
        doc=self.fixture();doc['bones'][4]['rotation']=0
        with self.assertRaisesRegex(ValueError,'bend_ambiguous'):build_wave(doc)
        doc=self.fixture();doc['bones'][4]['parent']='chest'
        with self.assertRaisesRegex(ValueError,'arm_topology'):build_wave(doc)

    def test_unreachable_asymmetric_arm_rejected_without_clamping(self):
        doc=self.fixture();doc['bones'][5]['x']=.01
        with self.assertRaisesRegex(ValueError,'target_unreachable'):build_wave(doc)

    def test_failed_geometry_does_not_replace_playable_scene(self):
        doc=self.fixture();doc['skins']=[{'attachments':{'arm':{'arm':{'vertices':[1,3,0,0,1,1,3,1,0,1,1,3,0,1,1],'triangles':[0,1,2]}}}}]
        files={'skeleton.json':canonical_bytes(doc),'character-manifest.json':canonical_bytes({'profile':'ordinary-motionir-idle-v1'}),
               'numeric-reference.json':canonical_bytes({'animations':{'old':[]}})}
        with patch('autospine_workbench.targets.character43.wave_package.inspect',return_value={'passed':False,'records':[{'slot':'arm','passed':False}]}):
            result=append_wave(files)
        self.assertEqual(result['skeleton.json'],files['skeleton.json'])
        self.assertEqual(json.loads(result['character-manifest.json'])['motion_readiness'][0]['status'],'blocked')
        passed=append_wave(files)
        self.assertIn('wave-left',json.loads(passed['skeleton.json'])['animations'])
