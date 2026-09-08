from copy import deepcopy
import unittest
from PIL import Image,ImageDraw
from autospine_workbench.asset.planning.wing_color_ownership import closed_envelope,transfer
from autospine_workbench.asset.planning.wing_edge_ownership import encode,decode


class ColorTests(unittest.TestCase):
    def ring(self):
        image=Image.new('RGBA',(9,9));ImageDraw.Draw(image).rectangle((1,1,7,7),outline=(50,40,30,255))
        return image

    def test_closed_vs_open_contour(self):
        ring=self.ring();mask,report=closed_envelope(ring)
        self.assertEqual(report['closed_interior_pixels'],25);self.assertEqual(sum(mask),49)
        ring.putpixel((4,1),(0,0,0,0));mask,report=closed_envelope(ring)
        self.assertEqual(report['closed_interior_pixels'],0);self.assertFalse(report['eligible'])

    def test_offset_transfer_and_exact_preservation(self):
        ring=self.ring();donor=Image.new('RGBA',(3,3),(80,140,240,180));parts={'wing':encode(ring)}
        inputs=(encode(donor),[13,23],parts,{'wing':[10,20]});before=deepcopy(inputs)
        combined,transfers,residual,report=transfer(*inputs)
        self.assertEqual(inputs,before);self.assertEqual(report['counts']['transferred'],9)
        self.assertEqual(decode(transfers['wing']).getpixel((3,3)),(80,140,240,180))
        self.assertEqual(decode(combined['wing']).getpixel((3,3)),(80,140,240,180))
        self.assertEqual(decode(combined['wing']).getpixel((1,1)),ring.getpixel((1,1)))
        self.assertFalse(decode(residual).getbbox());self.assertTrue(report['donor_reconstruction_exact'])
        self.assertEqual(transfer(*inputs),(combined,transfers,residual,report))

    def test_ambiguous_and_outside_stay_unassigned(self):
        raw=encode(self.ring());donor=Image.new('RGBA',(9,9),(10,20,30,255))
        combined,_,residual,report=transfer(encode(donor),[0,0],{'a':raw,'b':raw},{'a':[0,0],'b':[0,0]})
        self.assertEqual(report['counts'],dict(transferred=0,ambiguous=49,outside_closed_envelopes=32))
        self.assertEqual(decode(residual).tobytes(),donor.tobytes());self.assertEqual(combined['a'],raw)
