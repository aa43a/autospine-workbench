import json
from pathlib import Path
import unittest
from autospine_workbench.targets.character43.camera_track import validate, sample, at_times
from autospine_workbench.targets.character43.camera_projection import prepare
from autospine_workbench.targets.character43.oblique_motion import project


class CameraTrackTests(unittest.TestCase):
    def test_shared_browser_contract(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/camera-track-v1.json').read_bytes())
        for case in fixture['cases']:
            keys=validate(case['keys'],case['duration'])
            for time,yaw in case['samples']:
                self.assertAlmostEqual(sample(keys,time),yaw)

    def test_invalid_values_do_not_become_camera_angles(self):
        for keys in ([{'time':0,'yaw':True}], [{'time':0,'yaw':float('nan')}],
                     [{'time':0,'yaw':0},{'time':0,'yaw':360}], [{'time':0,'yaw':3601}]):
            with self.assertRaises(ValueError):validate(keys,2)
        with self.assertRaises(ValueError):at_times([{'time':0,'yaw':0}],[0,1,.5],2)

    def test_one_basis_for_all_observations_and_no_scene_origin_orbit(self):
        times=[0,.5,1,1.5,2];keys=[{'time':0,'yaw':0},{'time':2,'yaw':360}]
        roots=[(100+i,200,300) for i in range(5)]
        centers=[(x,y+2,z+3) for x,y,z in roots]
        vectors={'arm':[(1,0,0)]*5,'leg':[(1,3,2)]*5}
        result=prepare(vectors,roots,centers,times,10,keys,2)
        for i,yaw in enumerate(result['yaw_degrees']):
            self.assertEqual(result['vectors']['leg'][i],project(vectors['leg'][i],yaw))
            self.assertEqual(result['roots'][i],project((i,0,0),yaw))
            self.assertEqual(result['hip_centers'][i],project((i,2,3),yaw))
        self.assertEqual([r['frame'] for r in result['issues'] if r['reason']=='camera_direction_unobservable'],[1,3])
        self.assertTrue(any(r['reason']=='rear_surface_not_provided' for r in result['surface_issues']))
        shifted=lambda points:[tuple(v+offset for v,offset in zip(p,(123,456,-321))) for p in points]
        moved=prepare(vectors,shifted(roots),shifted(centers),times,10,keys,2)
        for field in ['vectors','roots','hip_centers','issues','visibility']:
            self.assertEqual(result[field],moved[field])

    def test_identity_is_deterministic_and_includes_full_turn(self):
        args=({'arm':[(1,2,3)]*3},[(0,0,0)]*3,[(0,1,0)]*3,[0,1,2],10)
        keys=[{'time':0,'yaw':0},{'time':2,'yaw':360}]
        first=prepare(*args,keys,2)
        self.assertEqual(first,prepare(*args,keys,2))
        self.assertNotEqual(first['projection_sha256'],prepare(*args,[{'time':0,'yaw':0}],2)['projection_sha256'])
