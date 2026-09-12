from copy import deepcopy
import math
import unittest
from autospine_workbench.targets.character43.drape_direction import apply
from autospine_workbench.targets.character43.affine_pose import matrices
from test_character_wave import WaveTests
from autospine_workbench.targets.character43.wave_motion import build_wave


def fixture():
    doc, _ = build_wave(WaveTests().fixture())
    doc['bones'].append(dict(name='cloth-fabric', parent='forearm_l', x=10, y=0, rotation=-50))
    doc['skins'] = [{'attachments': {'fabric': {}}}]
    return doc


class DirectionTests(unittest.TestCase):
    def test_holds_world_direction_and_wrist_position_between_keys(self):
        doc = fixture(); before = deepcopy(doc)
        result, report = apply(doc, 'wave-left', ['cloth-fabric'])
        setup = matrices(doc, 'wave-left', 0)['cloth-fabric']
        for i in range(101):
            t = i*.02; base = matrices(doc, 'wave-left', t); changed = matrices(result, 'wave-left', t)
            self.assertAlmostEqual(math.atan2(changed['cloth-fabric'][2], changed['cloth-fabric'][0]),
                                   math.atan2(setup[2], setup[0]), places=10)
            self.assertEqual(changed['cloth-fabric'][4:], base['cloth-fabric'][4:])
            self.assertEqual(changed['hand_l'], base['hand_l'])
        self.assertEqual(doc, before)
        self.assertEqual(report['authority'], 'none')

    def test_existing_driver_and_wrong_anchor_fail(self):
        doc = fixture(); doc['bones'][-1]['x'] = 11
        with self.assertRaisesRegex(ValueError, 'helper_anchor'):
            apply(doc, 'wave-left', ['cloth-fabric'])
        doc = fixture(); doc['animations']['wave-left']['bones']['cloth-fabric'] = {}
        with self.assertRaisesRegex(ValueError, 'existing_driver'):
            apply(doc, 'wave-left', ['cloth-fabric'])

    def test_scaled_or_curved_ancestors_not_silently_approximated(self):
        for kind in ('scale', 'curve'):
            doc = fixture()
            if kind == 'scale': doc['bones'][0]['scaleX'] = 2
            else: doc['animations']['wave-left']['bones']['forearm_l']['rotate'][0]['curve'] = [0, 0, 1, 1]
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                apply(doc, 'wave-left', ['cloth-fabric'])
