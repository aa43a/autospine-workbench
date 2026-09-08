"""Conservative faint-edge transfer, setup equivalence and immutable target/rig."""
from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
import unittest
from PIL import Image
from autospine_workbench.asset.planning.wing_edge_ownership import refine,encode,decode
from autospine_workbench.benchmark.wing_spine_preview import build as base_build
from autospine_workbench.benchmark.wing_edge_preview import build,verify
from tests import test_wing_spine_preview as base_tests


class EdgeTests(unittest.TestCase):
    def parts(self):
        a=Image.new('RGBA',(8,2));a.putpixel((0,0),(20,30,40,255))
        b=Image.new('RGBA',a.size);b.putpixel((4,0),(90,80,70,255))
        residual=Image.new('RGBA',a.size)
        for x,y,alpha in [(1,0,3),(2,0,5),(6,0,7),(7,1,2),(0,1,8)]:residual.putpixel((x,y),(90,40,20,alpha))
        return {'a':encode(a),'b':encode(b)},encode(residual)

    def test_unique_ambiguous_unselected_and_opaque(self):
        parts,rest=self.parts();before=deepcopy((parts,rest))
        outputs,residual,report=refine(parts,rest,{'a'})
        self.assertEqual((parts,rest),before)
        self.assertEqual(report['counts'],dict(transferred=1,ambiguous=1,no_nearby_owner=1,unselected_owner=1,opaque_residual=1))
        self.assertEqual(decode(outputs['a']).getpixel((1,0)),(90,40,20,3))
        self.assertEqual(decode(residual).getpixel((2,0)),(90,40,20,5))
        old=decode(rest);new=decode(residual)
        for raw in parts.values():old=Image.alpha_composite(old,decode(raw))
        for raw in outputs.values():new=Image.alpha_composite(new,decode(raw))
        self.assertEqual(old.tobytes(),new.tobytes())
        self.assertEqual(refine(parts,rest,{'a'}),(outputs,residual,report))

    def test_no_recursive_growth_and_bad_partition(self):
        a=Image.new('RGBA',(5,1));a.putpixel((0,0),(30,40,50,255));r=Image.new('RGBA',a.size)
        for x in (1,2,3):r.putpixel((x,0),(30,40,50,4))
        _,residual,report=refine({'a':encode(a)},encode(r),{'a'})
        self.assertEqual(report['counts']['transferred'],2)
        self.assertEqual(decode(residual).getpixel((3,0))[3],4)
        with self.assertRaises(ValueError):refine({'a':encode(a)},encode(r),{'missing'})
        r.putpixel((0,0),(30,40,50,4))
        with self.assertRaises(ValueError):refine({'a':encode(a)},encode(r),{'a'})

    def test_bundle_preserves_tracks_target_and_rejects_tampering(self):
        args=base_tests.WingSpineTests().fixture();base,files=base_build(*args);files.pop('preview-manifest.json')
        report,outputs=build(base,files)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-edge-preview-v1.schema.json').read_text()))
        self.assertNotIn('changes',report['edge_ownership'])
        self.assertEqual(report['edge_ownership']['changes_sha256'],sha256(outputs['edge-ownership.json']).hexdigest())
        for key in ('skeleton.json','editor/skeleton.json','skeleton.atlas','editor/images/topwear.png','textures/topwear.png','draft.json'):
            self.assertEqual(outputs[key],files[key])
        self.assertEqual(verify(report,base,files),report)
        bad=deepcopy(report);bad['review_queue']=[]
        with self.assertRaises(ValueError):verify(bad,base,files)
        self.assertFalse(report['review_queue'][0]['automatic_removal'])
        files['skeleton.json']=b'changed'
        with self.assertRaises(ValueError):build(base,files)
