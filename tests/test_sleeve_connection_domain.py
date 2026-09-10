import unittest
from copy import deepcopy
from autospine_workbench.asset.planning.sleeve_connection_domain import domain,retain


class ConnectionDomainTests(unittest.TestCase):
    def test_shared_garment_can_move_but_hand_and_unknown_stay_fixed(self):
        tri=[[0,1,2],[1,2,3],[2,3,4],[3,4,5]]
        assignments=[dict(role=r) for r in ['hanging_cloth','sleeve','cuff','hand']]
        result=domain(tri,assignments)
        self.assertEqual(result['free_vertices'],[0,1,2])
        self.assertEqual(result['protected_vertices'],[3,4,5])
        assignments[3]['role']='unknown'
        self.assertEqual(domain(tri,assignments)['anchors'],[3,4,5])

    def test_no_vertex_order_or_role_guess_and_bad_inventory(self):
        a=domain([[0,1,2]],[dict(role='hand')]);self.assertEqual(a['free_vertices'],[])
        with self.assertRaises(ValueError):domain([[0,1,2]],[])
        with self.assertRaises(ValueError):retain(dict(schema='a'),dict(schema='b'))

    def test_regression_discards_new_domain_and_tracks(self):
        qa=dict(inversions=0,min_area_ratio=1.,max_area_ratio=1.,max_edge_stretch=1.,bad_triangles=[])
        track=dict(bone_id='hand',amplitudes=[0,30,0],qa=[deepcopy(qa) for _ in range(129)],failed_ticks=0)
        baseline=dict(schema='autospine.sleeve-motion-envelope/v1',source_sha256='a'*64,skeleton_sha256='b'*64,project_id='fixture',
            authority='none',production_authorized=False,
            records=[dict(layer_id='layer',component_id='component',tracks=[track])])
        trial=deepcopy(baseline);r=trial['records'][0];r['correction_domain']={'free_vertices':[0]}
        r['tracks'][0]['qa'][1].update(inversions=1,min_area_ratio=-1,bad_triangles=[0]);r['tracks'][0]['failed_ticks']=1
        chosen=retain(trial,baseline)['records'][0]
        self.assertFalse(chosen['connection_trial']['selected'])
        self.assertNotIn('correction_domain',chosen)
        self.assertEqual(chosen['tracks'],baseline['records'][0]['tracks'])
