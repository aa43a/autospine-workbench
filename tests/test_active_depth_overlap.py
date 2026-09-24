from copy import deepcopy
from io import BytesIO
import unittest
from PIL import Image

from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.active_depth_overlap import ActiveProbe, recheck


class ActiveDepthOverlapTests(unittest.TestCase):
    def fixture(self):
        doc, files = fixture()
        variant = deepcopy(doc['skins'][0]['attachments']['a']['a'])
        variant['path'] = 'transparent'
        doc['skins'][0]['attachments']['a']['side'] = variant
        stream = BytesIO(); Image.new('RGBA', (2, 2)).save(stream, format='PNG')
        files['images/transparent.png'] = stream.getvalue()
        doc['animations']['test']['slots'] = {'a': {'attachment': [
            dict(time=0, name='a'), dict(time=1, name='side'), dict(time=2, name='a'), dict(time=3, name=None)]}}
        return doc, files

    def test_texture_switch_reverse_seek_and_hidden(self):
        doc, files = self.fixture(); probe = ActiveProbe(doc, files, 'test')
        for time, expected in ((0, 4), (1, 0), (2, 4), (1.5, 0), (.5, 4), (3, 0)):
            with self.subTest(time=time):
                self.assertEqual(probe.pair('a', 'b', time)['overlap_pixels'], expected)
        budget = probe.remaining
        self.assertEqual(probe.pair('b', 'a', 1)['overlap_pixels'], 0)
        self.assertEqual(probe.remaining, budget)

    def test_new_attachment_deform_is_sampled(self):
        doc, files = self.fixture()
        doc['skins'][0]['attachments']['a']['side']['path'] = 'a'
        doc['animations']['test']['attachments'] = {'default': {'a': {'side': {
            'deform': [dict(time=0, vertices=[10, 0]*4)]}}}}
        probe = ActiveProbe(doc, files, 'test')
        self.assertEqual(probe.pair('a', 'b', 0)['overlap_pixels'], 4)
        self.assertEqual(probe.pair('a', 'b', 1)['overlap_pixels'], 0)

    def test_report_retains_actual_identity(self):
        doc, files = self.fixture()
        depth = dict(pairs=[dict(arm_slot='a', torso_slot='b', setup_front_slot='a', samples=[
            dict(tick=1000000, ambiguous=False, current_front_slot='a')])])
        report = recheck(doc, files, 'test', depth, sparse=True)
        overlap = report['pairs'][0]['samples'][0]['overlap']
        self.assertEqual(overlap['active_attachments']['a'], 'side')
        self.assertEqual(overlap['overlap_pixels'], 0)
