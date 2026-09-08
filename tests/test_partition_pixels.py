"""Independent byte, alpha-composite, topology, and ambiguous-edge checks."""
from copy import deepcopy
import hashlib
from io import BytesIO
import unittest

from PIL import Image
from autospine_workbench.asset.joints.chain_coverage import _components
from autospine_workbench.asset.joints.partition_pixels import partition, png


def fixture():
    image=Image.new('RGBA',(12,8));image.putpixel((0,0),(9,2,4,0))
    for x in (1,2,8,9):
        for y in range(2,6):image.putpixel((x,y),(30,60,90,180))
    for x in range(3,8):image.putpixel((x,3),(12,90,240,4))
    image.putpixel((0,7),(255,1,4,3));image.putpixel((11,7),(40,70,80,255))
    raw=png('RGBA',image.size,image.tobytes())
    source={'bbox':[100,200,112,208],'image_sha256':hashlib.sha256(raw).hexdigest()}
    components=_components(image.getchannel('A').tobytes(),12,8,(100,200))[:2]
    for c in components:c['side']='l' if c['centroid'][0]<105 else 'r'
    return raw,source,{'components':components},image


class PartitionPixelsTests(unittest.TestCase):
    def test_exact_rgba_and_visible_composite(self):
        raw,source,proposal,image=fixture();before=deepcopy((source,proposal))
        files,qa=partition(raw,source,proposal)
        parts=[Image.open(BytesIO(files[name+'.png'])) for name in ('left','right','residual')]
        rebuilt=bytes(sum(values) for values in zip(*(part.tobytes() for part in parts)))
        self.assertEqual(rebuilt,image.tobytes())
        composite=Image.new('RGBA',image.size)
        for part in parts:composite=Image.alpha_composite(composite,part)
        for y in range(8):
            for x in range(12):
                if image.getpixel((x,y))[3]:self.assertEqual(composite.getpixel((x,y)),image.getpixel((x,y)))
                self.assertLessEqual(sum(part.getpixel((x,y))[3]>0 for part in parts),1)
        self.assertEqual(parts[2].getpixel((0,0)),(9,2,4,0))
        self.assertEqual(qa['source_rgba_sha256'],qa['reconstructed_rgba_sha256'])
        self.assertEqual((source,proposal),before)
        self.assertEqual(partition(raw,source,proposal),(files,qa))

    def test_tied_and_disconnected_edges_residual_satellite_retained(self):
        raw,source,proposal,_=fixture();files,qa=partition(raw,source,proposal)
        mask=Image.open(BytesIO(files['ownership.png']))
        self.assertEqual(mask.getpixel((5,3)),3)
        self.assertEqual(mask.getpixel((0,7)),3)
        self.assertEqual(mask.getpixel((3,3)),1)
        self.assertEqual(mask.getpixel((7,3)),2)
        self.assertEqual(mask.getpixel((11,7)),2)
        self.assertEqual(len(qa['satellite_components']),1)
        self.assertEqual(sum(qa['low_alpha_pixel_counts'].values()),6)

    def test_changed_pixels_components_dimensions_rejected(self):
        raw,source,proposal,_=fixture()
        with self.assertRaisesRegex(ValueError,'image_changed'):partition(raw+b'x',source,proposal)
        changed=deepcopy(proposal);changed['components'][0]['area']+=1
        with self.assertRaisesRegex(ValueError,'component_changed'):partition(raw,source,changed)
        changed=deepcopy(proposal);changed['components'][0]['id']=999
        with self.assertRaisesRegex(ValueError,'component_missing'):partition(raw,source,changed)
        changed=deepcopy(source);changed['bbox'][2]+=1
        with self.assertRaisesRegex(ValueError,'image_invalid'):partition(raw,changed,proposal)
