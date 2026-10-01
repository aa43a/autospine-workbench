"""A narrow fixed/free seam must not suppress the entire clothing response."""
from copy import deepcopy
import math
import unittest

from autospine_workbench.targets.character43 import joint_cloth_falloff as material
from autospine_workbench.targets.character43.joint_secondary_mesh import cloth
from autospine_workbench.targets.character43.joint_secondary import _points, defaults, normalize
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.joint_secondary_guard import protect
from autospine_workbench.targets.character43.joint_animation_config import defaults as editor_defaults, normalize as editor_normalize


def seam_scene():
    # Deliberately narrow first free row; even a small residual body weight
    # fixes its neighbor, as it does in a repaired waist transition.
    points = [(x, -y) for y in (0., 100., 102., 200.) for x in (0., 20.)]
    triangles = [[2*i, 2*i+1, 2*i+3] for i in range(3)] + [[2*i, 2*i+3, 2*i+2] for i in range(3)]
    flat = []
    for vi, (x, y) in enumerate(points):
        if vi < 4:
            flat.extend([2, 0, x, y, .004, 1, -y, x, .996])
        else:
            flat.extend([1, 1, -y, x, 1.])
    return dict(bones=[dict(name='root',x=0.,y=0.,rotation=0.), dict(name='skirt_helper', parent='root',x=0.,y=0., rotation=-90., length=100.)],
        slots=[dict(name='cloth', bone='root', attachment='cloth')],
        skins=[dict(attachments={'cloth': {'cloth': dict(type='mesh', uvs=[0., 0.]*len(points),
            triangles=sum(triangles, []), vertices=flat)}})], animations={'move': {}})


class ClothFalloffTests(unittest.TestCase):
    def test_topology_distance_is_scale_independent_and_unanchored_regions_stay_fixed(self):
        points = [(0., y) for y in (0., 1., 2., 100.)] + [(10., 0.), (10., 1.), (11., 1.)]
        triangles = [[0, 1, 2], [1, 2, 3], [4, 5, 6]]
        values, report = material.falloff(points, triangles, [0])
        scaled, _ = material.falloff([(3*x+19, 3*y-71) for x,y in points], triangles, [0])
        self.assertLess(max(abs(a-b) for a,b in zip(values,scaled)), 1e-12)
        self.assertEqual(values[0], 0.); self.assertEqual(values[3], 1.)
        self.assertLess(values[1], .001); self.assertEqual(values[4:], [0., 0., 0.])
        self.assertEqual(report['unanchored_vertices'], [4,5,6])
        self.assertEqual(report['transition_width_px'], 100.)

    def test_tiny_rooted_island_uses_the_same_release_width_as_main_cloth(self):
        points = [(0.,0.),(0.,10.),(0.,100.),(200.,0.),(200.,1.),(201.,1.)]
        values, report = material.falloff(points, [[0,1,2],[3,4,5]], [0,3])
        self.assertEqual(values[2], 1.)
        self.assertLess(values[4], .001); self.assertLess(values[5], .001)
        self.assertEqual(report['unanchored_vertices'], [])
        self.assertEqual(len(report['rooted_component_depths_px']), 2)

    def test_cloning_preserves_sparse_deforms_and_fixed_vertices_at_every_pose(self):
        for profile in (material.LEGACY, material.PROFILE):
            source = seam_scene(); size = 24
            source['animations']['move'] = dict(bones={'root': {'rotate': [dict(time=0,value=0),dict(time=2,value=13)]}},
                attachments={'default': {'cloth': {'cloth': {'deform': [
                    dict(time=0, offset=2, vertices=[.2,-.3]),
                    dict(time=1, vertices=[.2*math.sin(i) for i in range(size)]),
                    dict(time=2, vertices=[0.]*size)]}}}})
            out = deepcopy(source); record = cloth(out,'cloth',['skirt_helper'],response_profile=profile)
            self.assertGreater(record['movable_vertices'], 0)
            for t in (0., .2, .9, 1., 1.49, 2.):
                before = _points(source,'move',t,'cloth'); after = _points(out,'move',t,'cloth')
                self.assertLess(max(math.dist(a,b) for a,b in zip(before,after)), 1e-10)
            out['animations']['move']['bones']['m5-response-skirt_helper']={'rotate':[dict(time=0,value=10.)]}
            before=_points(source,'move',1.49,'cloth'); after=_points(out,'move',1.49,'cloth')
            for index in record['pinned_vertices']:
                self.assertLess(math.dist(before[index],after[index]),1e-10)
            curved=deepcopy(source)
            curved['animations']['move']['attachments']['default']['cloth']['cloth']['deform'][0]['curve']='stepped'
            cloth(curved,'cloth',['skirt_helper'],response_profile=profile)
            self.assertEqual(curved['animations']['move']['attachments']['default']['cloth']['cloth']['deform'][0]['curve'],'stepped')

    def test_smooth_seam_allows_response_while_legacy_thin_edge_still_needs_guard(self):
        gains = []
        for profile in (material.LEGACY, material.PROFILE):
            out=seam_scene(); record=cloth(out,'cloth',['skirt_helper'],response_profile=profile)
            baseline=deepcopy(out)
            out['animations']['move']['bones']={'m5-response-skirt_helper':{'rotate':[
                dict(time=0.,value=0.),dict(time=1/120,value=8.),dict(time=2/120,value=8.)]}}
            record.update(peak_response_deg=8.,springs=[dict(peak_angle_deg=8.)])
            times=[0.,1/120,2/120]; poses=[matrices(baseline,'move',t) for t in times]
            guard=protect(out,baseline,'move',[record],times,poses,_points,projected_overlap='diagnostic')[0]
            gains.append(guard['effective_gain'])
            self.assertGreaterEqual(guard['history'][-1]['min_area_ratio'],.55)
            self.assertLessEqual(guard['history'][-1]['max_edge_stretch'],1.9)
        self.assertLess(gains[0],1.); self.assertEqual(gains[1],1.)

    def test_new_editor_default_is_explicit_and_old_config_does_not_silently_migrate(self):
        old=defaults(wind=True); new=editor_defaults()
        self.assertNotIn('response_profile',old['cloth'])
        self.assertEqual(normalize(old,2.),old)
        self.assertEqual(editor_normalize(old,2.)['cloth'],old['cloth'])
        self.assertEqual(editor_normalize({'wind':old['wind']},2.)['cloth'],old['cloth'])
        self.assertEqual(new['cloth']['response_profile'],material.PROFILE)
        self.assertEqual(new['cloth']['max_angle'],8.)
        self.assertEqual(editor_normalize(new,2.),new)
        with self.assertRaisesRegex(ValueError,'cloth_response_profile'):
            normalize({'cloth': {'response_profile': 'unconstrained'}},2.)


if __name__ == '__main__': unittest.main()
