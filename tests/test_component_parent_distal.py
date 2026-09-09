from copy import deepcopy
import unittest
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_parent_distal import build
from autospine_workbench.asset.planning.component_local_correction import build as correction_build


class ComponentParentDistalTests(unittest.TestCase):
    def test_source_geometry_normalization_and_replay(self):
        args=limb_fixture();source=transition_build(mesh_build(*args),args[1],args[0]);before=deepcopy(source)
        result=build(source,args[0],args[1])
        self.assertEqual(result,build(source,args[0],args[1]));self.assertEqual(source,before)
        old=source['records'][0]['mesh'];new=result['records'][0]['mesh']
        for key in ('vertices_xy','uvs','triangles','raster_qa'):self.assertEqual(old[key],new[key])
        for a,b in zip(old['weights'],new['weights']):
            self.assertEqual(a[0]['weight'],b[0]['weight'])
            self.assertAlmostEqual(sum(w['weight'] for w in b),1)
        self.assertFalse(result['production_authorized'])
        # New weights receive a new correction source, not the old motion/deform identity.
        correction=correction_build(result,args[1])
        from autospine_workbench.resolved_project import canonical_sha256
        self.assertEqual(correction['source_sha256'],canonical_sha256(result))
        args[1]['bones'][0]['head_xy'][0]+=1
        with self.assertRaises(ValueError):build(source,args[0],args[1])
