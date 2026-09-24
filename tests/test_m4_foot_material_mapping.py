import unittest
import numpy as np
from m4_check_foot_material_connection import mapping


class FootMaterialMappingTests(unittest.TestCase):
    def test_static_uv_coefficients_follow_new_world_geometry(self):
        mesh=dict(uvs=[0,0,1,0,0,1],triangles=[0,1,2])
        weights=mapping(mesh,[[.25,.25]])
        np.testing.assert_allclose(weights@np.array([[10,20],[14,20],[10,24]]),[[11,21]])

    def test_outside_uv_is_not_replaced_with_nearest_point(self):
        with self.assertRaisesRegex(ValueError,'uncovered'):
            mapping(dict(uvs=[0,0,1,0,0,1],triangles=[0,1,2]),[[1,1]])
