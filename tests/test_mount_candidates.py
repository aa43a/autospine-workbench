"""Mount proximity is evidence, not an approved semantic or attachment."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import unittest
from PIL import Image
from tests.test_rig_planner import fixture
from autospine_workbench.asset.planning.mount_candidates import build, suggest, validate, category
from autospine_workbench.resolved_project import canonical_sha256


def inputs():
    candidate,_,_,_,images=fixture()
    candidate['layers'][0]['name']='objects'
    skeleton={'bones':[{'id':name,'head_xy':point,'tail_xy':point}
        for name,point in [('hand_l',[0,0]),('hand_r',[0,0]),('chest',[80,80]),('pelvis',[90,90])]]}
    plan={'source_candidate_sha256':canonical_sha256(candidate),'source_skeleton_sha256':canonical_sha256(skeleton),
          'scope':['layer-000'],'authority':'none','production_authorized':False}
    return candidate,skeleton,plan,images


class MountTests(unittest.TestCase):
    def test_replay_schema_and_no_automatic_selection(self):
        args=inputs();before=deepcopy(args);doc=build(*args)
        self.assertEqual(args,before);self.assertEqual(validate(*args,doc),doc)
        row=doc['layers'][0]
        self.assertIsNone(row['selected_option']);self.assertIsNone(row['confidence'])
        self.assertIn('accessory.held',row['semantic_hypotheses'])
        import jsonschema
        jsonschema.validate(doc,json.loads(Path('schemas/mount-candidates-v1.schema.json').read_text('utf-8')))
        bad=deepcopy(doc);bad['layers'][0]['mount_options'][0]['nearby']=True
        with self.assertRaises(ValueError): validate(*args,bad)

    def test_translation_invariance_and_ambiguous_nearby_anchors(self):
        candidate,skeleton,_,images=inputs();layer=candidate['layers'][0];raw=images['layer-000']
        result=suggest(layer,raw,skeleton,100)
        self.assertIn('multiple_nearby_mount_anchors',result['reason_codes'])
        self.assertIsNone(result['selected_option'])
        moved=deepcopy(layer);moved['bbox']=[v+200 for v in moved['bbox']]
        bones=deepcopy(skeleton)
        for bone in bones['bones']:
            for key in ('head_xy','tail_xy'):bone[key]=[v+200 for v in bone[key]]
        after=suggest(moved,raw,bones,100)
        self.assertEqual([o['distance_px'] for o in result['mount_options']],
                         [o['distance_px'] for o in after['mount_options']])

    def test_empty_missing_conflicting_and_changed_sources(self):
        candidate,skeleton,plan,images=inputs();layer=candidate['layers'][0]
        buffer=BytesIO();Image.new('RGBA',(4,4)).save(buffer,format='PNG');raw=buffer.getvalue()
        empty={**layer,'image_sha256':sha256(raw).hexdigest()}
        row=suggest(empty,raw,{'bones':[]},100)
        self.assertIn('no_opaque_alpha_support',row['reason_codes'])
        self.assertIn('required_bones_missing',row['reason_codes'])
        self.assertEqual(category({'name':'objects','semantic':'wear.skirt'}),'conflict')
        with self.assertRaises(ValueError):suggest(layer,b'changed',skeleton,100)
        with self.assertRaises(ValueError):suggest(layer,images['layer-000'],skeleton,float('nan'))
        plan['scope']=[]
        with self.assertRaises(ValueError):build(candidate,skeleton,plan,images)
