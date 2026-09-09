import json
import math
import subprocess
import unittest
from autospine_workbench.asset.planning.component_fk_qa import sample_fk,sample_track,build
from autospine_workbench.asset.planning.component_temporal_qa import sample
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_local_correction import build as correction_build


class ComponentFKTests(unittest.TestCase):
    def fixture(self):
        bones=[dict(id='foot_l',head_xy=[0,0],world_rotation_degrees=0)]
        mesh=dict(weights=[[dict(bone_id='foot_l',local_xy=[2,0],weight=1)]])
        angles=[-90,-60,-30,-15,0,15,30,60,90]
        frames=[sample_fk(mesh,bones,0,a) for a in angles]
        track=dict(bone_id='foot_l',angles=angles,original=frames,corrected=frames)
        return mesh,bones,track

    def test_fk_preserves_rigid_radius_while_vertex_lerp_shortens(self):
        mesh,bones,track=self.fixture()
        p=sample_track(mesh,bones,track,.5)[0]
        self.assertAlmostEqual(math.hypot(*p),2)
        self.assertLess(math.hypot(*sample(track['original'],.5)[0]),2)
        for i in range(9):self.assertEqual(sample_track(mesh,bones,track,i,True),track['original'][i])

    def test_javascript_matches_python_with_corrective_offset(self):
        mesh,bones,track=self.fixture()
        track['corrected']=[[[p[0]+i*.1,p[1]-.2] for p in frame] for i,frame in enumerate(track['original'])]
        expected=sample_track(mesh,bones,track,2.75,True)
        script="import{sampleFKTrack}from './web/modules/component-mesh-timeline.js';let s='';for await(const c of process.stdin)s+=c;const d=JSON.parse(s);console.log(JSON.stringify(sampleFKTrack(d.model,d.track,2.75,true)));"
        result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(dict(model=dict(bones=bones,weights=mesh['weights']),track=track)),text=True,capture_output=True,check=True)
        actual=json.loads(result.stdout)
        for a,b in zip(actual[0],expected[0]):self.assertAlmostEqual(a,b)

    def test_source_replay_and_separate_interpolation_evidence(self):
        args=limb_fixture();source=transition_build(mesh_build(*args),args[1],args[0]);correction=correction_build(source,args[1])
        result=build(source,correction,args[1]);self.assertEqual(result,build(source,correction,args[1]))
        self.assertEqual(len(result['rows']),3)
        self.assertEqual(len(result['rows'][0]['ticks']),33)
        self.assertFalse(result['continuous_time_proven'])
        correction['source_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,correction,args[1])
