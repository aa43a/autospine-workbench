import unittest
from autospine_workbench.targets.character43.projected_area_sampling import inspect


class SamplingTests(unittest.TestCase):
    def test_dual_floor_exposes_setup_failure_hidden_by_projection(self):
        document=dict(bones=[dict(name='root',x=0,y=0,rotation=0)],
            skins=[dict(attachments={'mesh':{'mesh':dict(triangles=[0,1,2],
                vertices=[1,0,0,0,1, 1,0,1,0,1, 1,0,0,1,1])}})],
            animations={'motion':dict(bones={'root':{'scale':[dict(time=0,x=.8,y=1),dict(time=1,x=.8,y=1)]}},
                attachments={'default':{'mesh':{'mesh':{'deform':[
                    dict(time=0,vertices=[0,0,-.4,0,0,0]),dict(time=1,vertices=[0,0,-.4,0,0,0])
                ]}}}})})
        self.assertEqual(inspect(document,'motion',['mesh'])['failures'],[])
        result=inspect(document,'motion',['mesh'],dual_floor=True)
        self.assertEqual(len(result['failures']),3)
        self.assertAlmostEqual(result['failures'][0]['min_setup_ratio'],.48)

    def test_positive_endpoint_triangles_can_collapse_between_deform_keys(self):
        # Both endpoint triangles have positive area; linear interpolation between
        # the original and a half-turned shape collapses all points at t=.5.
        document=dict(bones=[dict(name='root',x=0,y=0,rotation=0)],
            skins=[dict(attachments={'mesh':{'mesh':dict(triangles=[0,1,2],
                vertices=[1,0,0,0,1, 1,0,1,0,1, 1,0,0,1,1])}})],
            animations={'motion':dict(bones={},attachments={'default':{'mesh':{'mesh':{'deform':[
                dict(time=0,vertices=[0,0,0,0,0,0]),dict(time=1,vertices=[0,0,-2,0,0,-2])
            ]}}}})})
        result=inspect(document,'motion',['mesh'])
        self.assertEqual(result['sampled_frames'],3)
        self.assertEqual(len(result['failures']),1)
        self.assertEqual(result['failures'][0]['time'],.5)
        self.assertFalse(result['failures'][0]['at_key'])
        self.assertEqual(result['failures'][0]['inversions'],1)
