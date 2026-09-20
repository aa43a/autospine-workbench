from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from autospine_workbench.bvh_motion_compiler import compile_bvh_motion
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from autospine_workbench.targets.character43.oblique_motion import compile_candidate, project
from autospine_workbench.targets.character43.oblique_source import extract
from test_mixamo_map import source


class ObliqueTests(unittest.TestCase):
    def setUp(self):
        self.raw=source(); self.bvh=parse_bvh(self.raw)
        self.mapping=build_map(self.bvh,clip_id='oblique.test',reference_length=10,
                               screen_x='+X',screen_y='-Y',depth='+Z')
        self.base=compile_bvh_motion(self.raw,self.mapping).document
        with TemporaryDirectory() as temp:
            path=Path(temp); (path/'map.json').write_text(json.dumps(self.mapping))
            self.data=extract(SimpleNamespace(path=path,source_kind='bvh',raw_bvh=self.raw))

    def test_zero_yaw_preserves_existing_tracks_and_source(self):
        original=deepcopy(self.base)
        motion,receipt=compile_candidate(self.base,*self.data,0)
        self.assertEqual(motion['tracks'],self.base['tracks'])
        self.assertEqual(self.base,original)
        self.assertNotEqual(motion['clip_id'],self.base['clip_id'])
        self.assertEqual(receipt['authority'],'none')

    def test_yaw_is_orthogonal_and_side_basis_matches(self):
        point=(3,4,5)
        for yaw in (-90,-30,0,30,90):
            self.assertAlmostEqual(sum(v*v for v in project(point,yaw)),50)
        x,y,z=project(point,90)
        self.assertAlmostEqual(x,-5); self.assertEqual(y,4); self.assertAlmostEqual(z,3)

    def test_oblique_candidate_is_deterministic_and_independently_identified(self):
        a=compile_candidate(self.base,*self.data,30)
        self.assertEqual(a,compile_candidate(self.base,*self.data,30))
        self.assertNotEqual(a[1]['motion_sha256'],compile_candidate(self.base,*self.data,0)[1]['motion_sha256'])

    def test_invalid_yaw_or_degenerate_projection_is_rejected(self):
        for yaw in (float('nan'),91,True):
            with self.assertRaises(ValueError): compile_candidate(self.base,*self.data,yaw)
        vectors,roots,reference=deepcopy(self.data)
        key=next(iter(vectors)); vectors[key]=[(0,0,1)]*len(roots)
        with self.assertRaisesRegex(ValueError,'degenerate'):
            compile_candidate(self.base,vectors,roots,reference,0)

    def test_precision_is_explicit_and_part_of_identity(self):
        a=compile_candidate(self.base,*self.data,30,precision=5)
        b=compile_candidate(self.base,*self.data,30,precision=12)
        self.assertNotEqual(a[0]['clip_id'],b[0]['clip_id'])
        self.assertEqual(a[1]['precision_decimals'],5)
        with self.assertRaisesRegex(ValueError,'precision'):
            compile_candidate(self.base,*self.data,30,precision=6)


if __name__=='__main__': unittest.main()
