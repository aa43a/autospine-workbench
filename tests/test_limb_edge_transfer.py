from copy import deepcopy
import unittest
from PIL import Image
from autospine_workbench.asset.planning.wing_edge_ownership import encode, decode
from autospine_workbench.asset.planning.limb_edge_transfer import transfer


def fixture():
    a=Image.new('RGBA',(8,8));a.putpixel((2,2),(10,20,30,255))
    b=Image.new('RGBA',(8,8));r=Image.new('RGBA',(8,8))
    r.putpixel((3,2),(70,90,110,4));r.putpixel((5,2),(70,90,110,4));r.putpixel((2,3),(100,80,60,8))
    attachment=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
    return {'a':encode(a),'b':encode(b)},encode(r),{'a':attachment,'b':deepcopy(attachment)}


class LimbEdgeTests(unittest.TestCase):
    def test_exact_local_transfer_opaque_and_no_growth(self):
        parts,residual,attachments=fixture();before=deepcopy((parts,residual,attachments))
        out,rest,qa=transfer(parts,residual,attachments,[[3,2],[5,2],[2,3]])
        self.assertEqual(qa['counts']['transferred'],1);self.assertEqual(qa['counts']['no_neighbor'],1);self.assertEqual(qa['counts']['opaque'],1)
        self.assertEqual(decode(out['a']).getpixel((3,2)),(70,90,110,4))
        old=decode(residual);new=decode(rest)
        for n in parts:old.alpha_composite(decode(parts[n]));new.alpha_composite(decode(out[n]))
        self.assertEqual(old.tobytes(),new.tobytes());self.assertEqual((parts,residual,attachments),before)
        self.assertEqual(transfer(parts,residual,attachments,[[3,2],[5,2],[2,3]]),(out,rest,qa))

    def test_ambiguity_and_missing_mesh_coverage_preserve_residual(self):
        parts,residual,attachments=fixture();b=decode(parts['b']);b.putpixel((4,2),(10,20,30,255));parts['b']=encode(b)
        _,rest,qa=transfer(parts,residual,attachments,[[3,2]])
        self.assertEqual(qa['counts']['ambiguous'],1);self.assertEqual(decode(rest).tobytes(),decode(residual).tobytes())
        parts,residual,attachments=fixture();attachments['a']['uvs']=[0,0,.1,0,.1,.1,0,.1]
        _,rest,qa=transfer(parts,residual,attachments,[[3,2]])
        self.assertEqual(qa['counts']['outside_mesh'],1);self.assertEqual(decode(rest).tobytes(),decode(residual).tobytes())

    def test_unsampled_and_occupied_pixels_unchanged(self):
        parts,residual,attachments=fixture();a=decode(parts['a']);a.putpixel((3,2),(1,2,3,1));parts['a']=encode(a)
        out,rest,qa=transfer(parts,residual,attachments,[[3,2]])
        self.assertEqual(qa['counts']['occupied'],1)
        self.assertEqual(decode(rest).tobytes(),decode(residual).tobytes())
        for n in parts:self.assertEqual(decode(out[n]).tobytes(),decode(parts[n]).tobytes())

    def test_invalid_sample_rejected(self):
        with self.assertRaises(ValueError):transfer(*fixture(),[[-1,0]])
