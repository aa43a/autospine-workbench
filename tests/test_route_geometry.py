"""Geometry is normalized evidence, never semantic adoption or sleeve absence."""
from copy import deepcopy
import unittest
from autospine_workbench.automation.route_geometry import analyze, eligible_layers
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png


def fixture(scale=1, dx=0, dy=0, mask=lambda x,y: True):
    layer = dict(id='arm', name='handwear-l', canonical_role='body.hand', side='left',
                 bbox=dict(x=dx,y=dy,width=64*scale,height=64*scale))
    joints = [dict(id=k+'.left', x=dx+x*scale, y=dy+32*scale, source='derived',
                   review_state='manual_adjusted', decision_kind='manual_absolute')
              for k,x in [('shoulder',0),('elbow',32),('wrist',64)]]
    project = dict(resolved=dict(sha256='a'*64, layers=[layer], skeleton=dict(joints=joints)))
    pixels = b''.join(bytes([255,255,255,255 if mask(x//scale,y//scale) else 0])
                      for y in range(64*scale) for x in range(64*scale))
    return project, {'arm': encode_rgba_png(RgbaImage(64*scale,64*scale,pixels))}


class RouteGeometryTests(unittest.TestCase):
    def test_broad_and_narrow_are_readonly_not_semantics(self):
        args = fixture(); old = deepcopy(args); doc = analyze(*args)
        self.assertEqual(args, old); self.assertEqual(doc, analyze(*args))
        self.assertEqual(doc['authority'], 'none'); self.assertFalse(doc['production_authorized'])
        row = doc['records'][0]
        self.assertEqual(row['classification'], 'broad_off_axis_shape')
        self.assertEqual(len(row['image_sha256']),64)
        self.assertTrue(all(j['manual_override'] for j in row['joint_evidence']))
        self.assertEqual(row['geometry']['sample_count'],4096)
        narrow = analyze(*fixture(mask=lambda x,y: 29<=y<=34))['records'][0]
        self.assertEqual(narrow['classification'], 'no_broad_shape_evidence')
        self.assertIn('narrow_shape_not_sleeveless_proof',narrow['reason_codes'])

    def test_translation_and_scale_invariance(self):
        a = analyze(*fixture())['records'][0]
        b = analyze(*fixture(scale=3,dx=900,dy=-50))['records'][0]
        for key in ('normalized_distance_median','normalized_distance_p90','off_axis_ratio'):
            self.assertAlmostEqual(a['geometry'][key],b['geometry'][key])
        self.assertEqual(a['connectivity'],b['connectivity'])
        self.assertEqual(b['geometry']['distance_p90_px'],3*a['geometry']['distance_p90_px'])

    def test_missing_side_image_joints_and_disconnected(self):
        p, images = fixture()
        self.assertIn('layer_image_missing',analyze(p,{})['records'][0]['reason_codes'])
        self.assertIn('layer_image_invalid',analyze(p,{'arm':b'bad'})['records'][0]['reason_codes'])
        p['resolved']['layers'][0]['bbox']['width']=63
        self.assertIn('layer_image_bbox_mismatch',analyze(p,images)['records'][0]['reason_codes'])
        p, images = fixture(); p['resolved']['layers'][0]['side']='unknown'
        self.assertIn('character_side_unknown',analyze(p,images)['records'][0]['reason_codes'])
        p, images = fixture(); p['resolved']['skeleton']['joints'][0]['x']=float('nan')
        self.assertIn('arm_joint_missing_or_nonfinite',analyze(p,images)['records'][0]['reason_codes'])
        split=analyze(*fixture(mask=lambda x,y:x<16 or x>47))['records'][0]
        self.assertEqual(split['connectivity']['significant_component_count'],2)
        self.assertIn('alpha_severely_disconnected',split['reason_codes'])
        self.assertEqual(split['classification'],'insufficient_evidence')

    def test_unreviewed_is_visible_and_nonarm_layers_ignored(self):
        p, images=fixture(); p['resolved']['skeleton']['joints'][0].update(review_state='unreviewed',decision_kind=None)
        row=analyze(p,images)['records'][0]
        self.assertFalse(row['joint_evidence'][0]['manual_override'])
        self.assertIn('arm_joints_unreviewed',row['reason_codes'])
        self.assertEqual(row['classification'],'insufficient_evidence')
        p['resolved']['layers'][0].update(name='face',canonical_role='face.base')
        self.assertEqual(eligible_layers(p),[]); self.assertEqual(analyze(p,images)['records'],[])


if __name__=='__main__': unittest.main()
