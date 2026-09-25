import unittest
from unittest.mock import patch
import numpy as np
from autospine_workbench.targets.character43.shoulder_contact_regions import constraints,solve
from autospine_workbench.targets.character43.shoulder_region_validation import inspect

POINTS=[[0.,0.],[2.,0.],[0.,2.]]
ROW=dict(slot='arm',points=POINTS,triangles=[[0,1,2]])
PREPARED=dict(context={'budget_px':2.},free=[2],locked=[],support=[dict(vertex=2,center=[0.,2.],radius=.2)])
IDENTITY=(1.,0.,0.,1.,0.,0.)


class RegionSequenceTests(unittest.TestCase):
    def test_near_duplicate_times_keep_geometry_checks_but_not_velocity_noise(self):
        def sample(doc,name,t):
            points=[p[:] for p in POINTS]
            if doc.get('trial') and t==1e-10:points[2][1]=2.3
            return {'arm':points},{}
        with patch('autospine_workbench.targets.character43.shoulder_region_validation.sample',side_effect=sample),patch('autospine_workbench.targets.character43.shoulder_region_validation.matrices',return_value={'chest':IDENTITY}):
            report=inspect({}, {'trial':True},[(ROW,PREPARED)],[0.,1e-10,1.])
        self.assertEqual(report['frames'],3);self.assertEqual(report['failures'][0]['time'],1e-10)
        self.assertEqual(report['near_time_samples_excluded_from_speed_only'],1)
        self.assertEqual(report['maximum_vertex_speed_px_s'],0)

    def test_region_transform_preserves_material_distance(self):
        fixed,regions=constraints(ROW,PREPARED,IDENTITY,(0.,-2.,3.,0.,5.,7.),POINTS)
        r=regions[0];np.testing.assert_allclose(r['center'],[1.,7.])
        np.testing.assert_allclose(np.array(r['inverse'])@np.array([-.4,0.]),[0.,.2])

    def test_failed_optimizer_seed_never_becomes_animation(self):
        for harmonic in (False,True):
            with patch('autospine_workbench.targets.character43.shoulder_contact_regions.refine',return_value=([[99.,99.]]*3,{'status':'no_feasible_candidate_found'})) as refine:
                points,report=solve(ROW,PREPARED,IDENTITY,IDENTITY,POINTS,harmonic_seed=harmonic)
            self.assertEqual(points,POINTS)
            self.assertIs(refine.call_args.args[4],POINTS)
            self.assertEqual(refine.call_args.args[6],PREPARED['context']['budget_px'])

    def test_interpolated_contact_failure_is_not_hidden_by_good_geometry(self):
        def sample(doc,name,t):
            points=[p[:] for p in POINTS]
            if doc.get('trial') and t==.5:points[2][1]=2.3
            return {'arm':points,'other':[[5.,5.]]},{}
        with patch('autospine_workbench.targets.character43.shoulder_region_validation.sample',side_effect=sample),patch('autospine_workbench.targets.character43.shoulder_region_validation.matrices',return_value={'chest':IDENTITY}):
            report=inspect({}, {'trial':True},[(ROW,PREPARED)],[0.,.5,1.])
        self.assertFalse(report['passed']);self.assertEqual(len(report['failures']),1)
        self.assertEqual(report['failures'][0]['time'],.5)
        self.assertFalse(report['failures'][0]['geometry']['bad_triangles'])
        self.assertGreater(report['failures'][0]['region_ratio'],1)

    def test_existing_pin_tolerance_does_not_relax_fixed_distal_vertices(self):
        prepared=dict(context={'budget_px':2.},free=[],locked=[2],support=[])
        for moved,expected in [(2,True),(0,False)]:
            def sample(doc,name,t):
                points=[p[:] for p in POINTS]
                if doc.get('trial'):points[moved][1]+=.001
                return {'arm':points},{}
            with patch('autospine_workbench.targets.character43.shoulder_region_validation.sample',side_effect=sample),patch('autospine_workbench.targets.character43.shoulder_region_validation.matrices',return_value={'chest':IDENTITY}):
                report=inspect({}, {'trial':True},[(ROW,prepared)],[0.,1.])
            self.assertEqual(report['passed'],expected)
