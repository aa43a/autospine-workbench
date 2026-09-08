"""Inward selection must not reward an outer contour's zero-distance overlap."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests.test_mount_contact import rect
from tests.test_rig_planner import fixture
from autospine_workbench.asset.planning.wing_root import analyze,build,validate,components
from autospine_workbench.resolved_project import canonical_sha256


class WingTests(unittest.TestCase):
    def test_components_face_torso_not_outer_overlap(self):
        source=rect(-30,0,12,20)|rect(20,0,12,20)
        target=rect(-31,0,4,20)|rect(30,0,4,20)
        result=analyze(source,target,[0,10],100)
        self.assertEqual(len(result),2)
        for row in result:
            self.assertTrue(row['roots'])
            for r in row['roots']:
                self.assertLess(abs(r['source_xy'][0]),abs(row['centroid_xy'][0]))
                self.assertFalse(r['target_opaque_at_root'])

    def test_small_components_and_undefined_direction_are_preserved(self):
        result=analyze({(100,100)}|rect(0,0,4,4),set(),[2,2],100)
        self.assertEqual(result[0]['reason_code'],'inward_direction_unobservable')
        self.assertEqual(result[1]['reason_code'],'small_component_retained_without_root')
        self.assertEqual(sum(r['area_pixels'] for r in result),17)

    def test_projection_translation_and_limits(self):
        source=rect(10,10,12,20);target=rect(0,0,60,60)
        a=analyze(source,target,[0,15],100)
        b=analyze({(x+100,y-50) for x,y in source},{(x+100,y-50) for x,y in target},[100,-35],100)
        self.assertEqual(a[0]['projected_target_coverage'],1)
        self.assertEqual([r['anchor_distance_px'] for r in a[0]['roots']],
                         [r['anchor_distance_px'] for r in b[0]['roots']])
        with self.assertRaises(ValueError):components({(2*x,0) for x in range(4097)})
        with self.assertRaises(ValueError):analyze(source,target,[0,0],float('nan'))

    def test_schema_replay_and_authority(self):
        candidate,_,_,_,images=fixture();source=candidate['layers'][0]
        target={**source,'layer_id':'layer-001'};candidate['layers'].append(target)
        images['layer-001']=images['layer-000']
        mounts={'layers':[{'layer_id':'layer-000','category':'wing'}],'character_height_px':100}
        contacts={'source_mount_sha256':canonical_sha256(mounts),'rows':[{
          'layer_id':'layer-000','name':'wings','bone_id':'chest','anchor_xy':[10,2],
          'relations':[{'target_layer_id':'layer-001'}]}]}
        previous={'source_contact_sha256':canonical_sha256(contacts),'authority':'none','production_authorized':False,
          'rows':[{'layer_id':'layer-000','target_layer_id':'layer-001','bone_id':'chest','candidates':[{'source_xy':[.5,.5]}]}]}
        args=(candidate,mounts,contacts,previous,images);before=deepcopy(args)
        doc=build(*args);self.assertEqual(args,before);self.assertEqual(validate(*args,doc),doc)
        self.assertFalse(doc['rows'][0]['occlusion_verified']);self.assertIsNone(doc['rows'][0]['selected_root'])
        import jsonschema
        jsonschema.validate(doc,json.loads(Path('schemas/wing-root-v1.schema.json').read_text('utf-8')))
        bad=deepcopy(doc);bad['rows'][0]['occlusion_verified']=True
        with self.assertRaises(ValueError):validate(*args,bad)


class ProjectionTests(unittest.TestCase):
    def test_same_pixels_and_disjoint_canvas(self):
        from autospine_workbench.asset.planning.wing_projection_similarity import compare
        candidate,_,_,_,images=fixture();layer=candidate['layers'][0];raw=images['layer-000']
        result=compare(layer,raw,layer,raw)
        self.assertEqual(result['overlap_pixels'],15)
        self.assertEqual(result['rgba_exact_pixels'],15)
        self.assertEqual(result['rgb_mae'],0)
        moved={**layer,'bbox':[100,100,104,104]}
        self.assertEqual(compare(layer,raw,moved,raw)['overlap_pixels'],0)

    def test_different_colors_do_not_count_as_duplicate_pixels(self):
        from hashlib import sha256
        from io import BytesIO
        from PIL import Image
        from autospine_workbench.asset.planning.wing_projection_similarity import compare
        candidate,_,_,_,images=fixture();layer=candidate['layers'][0]
        buffer=BytesIO();Image.new('RGBA',(4,4),(0,0,0,255)).save(buffer,format='PNG');raw=buffer.getvalue()
        target={**layer,'image_sha256':sha256(raw).hexdigest()}
        result=compare(layer,images['layer-000'],target,raw)
        self.assertEqual(result['overlap_pixels'],15)
        self.assertEqual(result['rgb_exact_pixels'],0)
        self.assertEqual(result['rgb_mae'],255)
