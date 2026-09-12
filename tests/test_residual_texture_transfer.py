import importlib.util
from io import BytesIO
import json
import unittest
from autospine_workbench.targets.character43.residual_texture_transfer import build


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional image analysis')
class TextureTransferTests(unittest.TestCase):
    def fixture(self):
        from PIL import Image
        def encoded(image):
            stream=BytesIO();image.save(stream,format='PNG');return stream.getvalue()
        mesh=dict(type='mesh',uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],
                  vertices=[v for x,y in [(0,0),(4,0),(4,4),(0,4)] for v in (1,0,x,y,1)])
        doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0)],animations={'idle':{}},
                 skins=[dict(attachments={name:{name:mesh} for name in ['rest','bound']})])
        source=Image.new('RGBA',(4,4));target=source.copy()
        for point,alpha in [((0,3),3),((3,0),3),((1,1),3),((0,2),8)]:source.putpixel(point,(100,50,20,alpha))
        target.putpixel((3,0),(200,10,10,5))
        return {'skeleton.json':json.dumps(doc).encode(),'skeleton.atlas':b'unchanged layout',
                'character-manifest.json':json.dumps({'layers':[{'layer_id':'source','regions':[
                    {'region_id':'rest','state':'static_reference'},{'region_id':'bound','state':'weighted_candidate'}]}]}).encode(),
                'images/rest.png':encoded(source),'images/bound.png':encoded(target)}

    def test_transfer_preserves_texel_composite_and_keeps_rejected_pixels(self):
        from PIL import Image
        files=self.fixture();snapshot=dict(files);result,report=build(files)
        self.assertEqual(files,snapshot)
        self.assertEqual(result['skeleton.json'],files['skeleton.json'])
        self.assertEqual(result['skeleton.atlas'],files['skeleton.atlas'])
        counts=report['rows'][0]['counts']
        self.assertEqual(counts,{'transferred':1,'target_alpha_collision':1,'full_pixel_coverage_required':1,'non_edge_alpha_requires_review':1})
        def composite(bundle):
            return Image.alpha_composite(Image.open(BytesIO(bundle['images/bound.png'])).convert('RGBA'),
                                         Image.open(BytesIO(bundle['images/rest.png'])).convert('RGBA')).tobytes()
        self.assertEqual(composite(result),composite(files));self.assertFalse(report['selected'])
        replay,_=build(result)
        self.assertEqual(replay['images/rest.png'],result['images/rest.png'])

    def test_uv_mismatch_cannot_transfer_and_aliases_must_match(self):
        files=self.fixture();doc=json.loads(files['skeleton.json'])
        doc['skins'][0]['attachments']['bound']['bound']['uvs']=[0,0,.9,0,.9,1,0,1]
        files['skeleton.json']=json.dumps(doc).encode();result,report=build(files)
        self.assertNotIn('transferred',report['rows'][0]['counts'])
        files=self.fixture();files['editor/images/rest.png']=b'wrong'
        with self.assertRaisesRegex(ValueError,'editor_texture_mismatch'):build(files)

    def test_union_transfers_shared_diagonal_texel_but_keeps_other_guards(self):
        files=self.fixture();legacy,_=build(files)
        result,report=build(files,coverage_profile='triangle-union-v2')
        self.assertEqual(report['coverage_profile'],'triangle-union-v2')
        self.assertEqual(report['rows'][0]['counts'],{'transferred':2,'target_alpha_collision':1,'non_edge_alpha_requires_review':1})
        self.assertEqual(result['skeleton.json'],files['skeleton.json'])
        self.assertEqual(build(files)[0],legacy)
