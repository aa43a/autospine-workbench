import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_surface_inventory import build,classify,route


class SurfaceInventoryTests(unittest.TestCase):
    def test_rendered_weights_override_slot_bone_and_ignore_unused_vertices(self):
        doc,_=fixture();doc['bones'][0]['name']='chest';doc['bones'].append(dict(name='head'))
        for slot in doc['slots']:slot['bone']='head'
        mesh=doc['skins'][0]['attachments']['a']['a']
        mesh['uvs'] += [0,0];mesh['vertices'] += [1,1,100,100,1]
        before=deepcopy(doc);report=build(doc)
        self.assertEqual(report['surfaces'][0]['role'],'torso');self.assertEqual(doc,before)
        mesh['vertices'][5]=-1
        with self.assertRaisesRegex(ValueError,'weights'):build(doc)

    def test_generated_garment_topology_must_be_complete(self):
        bones={'x-skirt_0_upper':dict(parent='pelvis',length=10),
               'x-skirt_0_lower':dict(parent='x-skirt_0_upper',length=10)}
        names={'chest','x-skirt_0_upper','x-skirt_0_lower'}
        self.assertEqual(classify(names,bones),'garment_plane_candidate')
        bones['x-skirt_0_upper']['parent']='head'
        self.assertEqual(classify(names,bones),'unmodeled')
        self.assertEqual(classify({'forearm_l','hand_l'},{}),'arm.l')
        self.assertEqual(classify({'thigh_r','foot_r'},{}),'leg.r')
        self.assertEqual(classify({'forearm_l','sleeve-helper'},{}),'unmodeled')

    def test_unknown_surfaces_keep_setup_policy_not_fake_depth(self):
        rows={'arm':[dict(body='hair',status='unmeasured'),dict(body='leg',status='unmeasured')]}
        original=deepcopy(rows)
        selected,held=route(rows,{'surfaces':[dict(slot='hair',role='unmodeled'),dict(slot='leg',role='leg.l')]})
        self.assertEqual(selected,{'arm':[rows['arm'][1]]})
        self.assertEqual(held,[dict(arm='arm',body='hair',role='unmodeled',policy='preserve_setup_without_depth_claim')])
        self.assertEqual(rows,original)
