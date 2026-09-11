from io import BytesIO
import unittest
from PIL import Image
from autospine_workbench.targets.character43.setup_raster import compare_setup


def png(color):
    out=BytesIO();Image.new('RGBA',(2,2),color).save(out,format='PNG');return out.getvalue()


class SetupRasterTests(unittest.TestCase):
    def setUp(self):
        self.doc={'slots':[{'name':'s','attachment':'a'}], 'skins':[{'attachments':{'s':{'a':{
            'type':'mesh','path':'source','uvs':[0,0,1,0,1,1,0,1]}}}}]}
        self.ref={'vertices':{'s':[[0,0],[2,0],[2,-2],[0,-2]]}}
        self.viewport={'width':2,'height':2,'left':0,'bottom':-2}

    def compare(self,source,frame):
        return compare_setup(self.doc,self.ref,{'images/source.png':png(source)},png(frame),self.viewport)[0]

    def test_identical_opaque_source_and_lost_visible_pixels(self):
        result=self.compare((200,40,80,255),(200,40,80,255))
        self.assertEqual(result['max_pma_channel_error'],0)
        lost=self.compare((200,40,80,255),(0,0,0,0))
        self.assertEqual(lost['missing_visible_pixels'],4)
        self.assertEqual(lost['pixels_error_over_2'],4)

    def test_low_alpha_rgb_is_not_opaque_noise(self):
        result=self.compare((240,240,240,1),(255,255,255,1))
        self.assertLess(result['max_pma_channel_error'],.1)
        self.assertEqual(result['faint_framebuffer_pixels'],4)
        self.assertEqual(result['unexpected_visible_pixels'],0)
        self.assertEqual(result['status'],'needs_review')

    def test_transformed_or_additive_input_does_not_get_false_comparison(self):
        self.ref['vertices']['s'][1][0]=3
        with self.assertRaisesRegex(ValueError,'transform_unsupported'):self.compare((0,0,0,0),(0,0,0,0))
        self.doc['slots'][0]['blend']='additive'
        with self.assertRaisesRegex(ValueError,'blend_unsupported'):self.compare((0,0,0,0),(0,0,0,0))
