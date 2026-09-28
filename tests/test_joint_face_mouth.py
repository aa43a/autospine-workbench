from copy import deepcopy
import unittest

from test_joint_face import fixture
from autospine_workbench.targets.character43.joint_face import apply, defaults
from autospine_workbench.targets.character43.joint_face_mouth import _ordered_names
from autospine_workbench.targets.character43.joint_face_mouth_asset import PNG
from autospine_workbench.png_rgba import decode_rgba_png


class JointFaceMouthTests(unittest.TestCase):
    def prepare(self):
        files, doc = fixture(); files['skeleton.atlas'] = b'original atlas\n'
        config = defaults(); config['enabled'] = True; config['mouth']['template_enabled'] = True
        config['mouth']['keys'] = [dict(time=0, open=0), dict(time=1, open=1), dict(time=2, open=0)]
        return files, doc, config

    def test_optional_template_is_transparent_setup_and_crossfades_with_original(self):
        files, doc, config = self.prepare(); before = deepcopy(doc)
        result, updates, report = apply(files, doc, 'body', config, [0, 1, 2])
        template = report['generated_templates'][0]; name = template['slot']
        self.assertEqual(doc, before)
        slot = next(s for s in result['slots'] if s['name'] == name)
        self.assertEqual(slot['color'], 'ffffff00')
        alpha = result['animations']['body']['slots']
        at = lambda target, time: next(k['value'] for k in alpha[target]['alpha'] if k['time'] == time)
        self.assertEqual((at(name, 0), at(name, 1), at(name, 2)), (0, 1, 0))
        self.assertEqual((at('layer-004', 0), at('layer-004', 1), at('layer-004', 2)), (1, 0, 1))
        self.assertGreater(template['min_scale_y'], 0)
        self.assertEqual(updates['textures/'+name+'.png'], PNG)
        self.assertEqual(files['skeleton.atlas'], b'original atlas\n')
        image = decode_rgba_png(PNG)
        self.assertEqual((image.width, image.height), (64, 48))
        self.assertEqual(image.pixels[3], 0)
        self.assertEqual(image.pixels[(24*64+32)*4+3], 255)

    def test_all_existing_draw_orders_preserve_original_relative_order(self):
        files, doc, config = self.prepare()
        names = [s['name'] for s in doc['slots']]
        # Move mouth in front of the body via a legal partial draw order.
        doc['animations']['body']['drawOrder'] = [dict(time=0),
            dict(time=1, offsets=[dict(slot='layer-004', offset=1)])]
        doc['animations']['untouched'] = deepcopy(doc['animations']['body'])
        result, _, report = apply(files, doc, 'body', config, [0, 1, 2])
        new_names = [s['name'] for s in result['slots']]
        new = report['generated_templates'][0]['slot']
        for animation in doc['animations']:
            for old_key, key in zip(doc['animations'][animation]['drawOrder'], result['animations'][animation]['drawOrder']):
                original = _ordered_names(names, old_key.get('offsets', []))
                actual = _ordered_names(new_names, key.get('offsets', []))
                self.assertEqual([n for n in actual if n != new], original)
                self.assertEqual(actual.index(new), actual.index('layer-004')+1)

    def test_disabled_template_does_not_add_assets_slots_or_mutate_input(self):
        files, doc, config = self.prepare()
        config['enabled'] = False
        result, updates, report = apply(files, doc, 'body', config, [0, 1, 2])
        self.assertEqual(result, doc); self.assertEqual(updates, {})
        config['enabled'] = True; config['mouth']['enabled'] = False
        result, updates, report = apply(files, doc, 'body', config, [0, 1, 2])
        self.assertEqual(len(result['slots']), len(doc['slots']))
        self.assertEqual(updates, {})
        self.assertEqual(report['generated_templates'], [])

    def test_alpha_conflict_skips_only_template_and_reports_missing(self):
        files, doc, config = self.prepare()
        doc['animations']['body']['slots'] = {'layer-004': {'alpha': [dict(time=0, value=.2)]}}
        result, updates, report = apply(files, doc, 'body', config, [0, 1, 2])
        self.assertIn('mouth_template', report['missing'])
        self.assertEqual(updates, {})
        self.assertEqual(result['animations']['body']['slots']['layer-004'], doc['animations']['body']['slots']['layer-004'])


if __name__ == '__main__':
    unittest.main()
