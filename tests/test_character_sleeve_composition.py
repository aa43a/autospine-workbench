"""Composition preserves source ownership, setup, weighted indices and motion."""
from copy import deepcopy
from io import BytesIO
import unittest

from autospine_workbench.targets.character43.sleeve_scene import compose_scene
from autospine_workbench.targets.character43.sleeve_package import subtract_components


def fixture():
    bone = dict(name='root', x=0, y=0, rotation=0, length=1)
    attachment = dict(type='mesh', path='arm', uvs=[0,0,1,0,0,1], triangles=[0,1,2],
                      vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1])
    base = dict(skeleton=dict(spine='4.3.26',x=0,y=-4,width=4,height=4),bones=[bone],constraints=[],
                slots=[dict(name='arm',bone='root',attachment='arm')],
                skins=[dict(name='default',attachments={'arm':{'arm':attachment}})],
                animations={'old':dict(bones={})})
    donor=deepcopy(base); donor['slots'][0].update(name='part',attachment='part')
    donor['skins'][0]['attachments']={'part':{'part':dict(attachment,path='part')}}
    donor['animations']={'flex':dict(bones={'root':dict(rotate=[dict(time=0,value=0)])},
                                   attachments={'default':{'part':{'part':{'deform':[dict(time=0,vertices=[0]*6)]}}}})}
    source={'layers':[dict(layer_id='arm',bbox=[0,0,4,4])]}
    skeleton={'bones':[dict(id='root',head_xy=[0,0],world_rotation_degrees=0)]}
    return base, donor, source, skeleton


class CharacterSleeveTests(unittest.TestCase):
    def test_exact_deform_and_residual_survive_without_old_motion(self):
        base, donor, source, skeleton=fixture(); before=deepcopy((base,donor))
        doc, owners=compose_scene(base,[dict(source_layer_id='arm',documents=[donor],residual_id='rest')],source,skeleton)
        self.assertEqual([s['name'] for s in doc['slots']],['part','rest'])
        self.assertEqual(doc['animations'],donor['animations'])
        self.assertEqual(owners,{'part':'arm','rest':'arm'})
        self.assertEqual(before,(base,donor))

    def test_incompatible_bones_and_motion_fail_closed(self):
        base, donor, source, skeleton=fixture()
        donor['bones'][0]['x']=1
        with self.assertRaisesRegex(ValueError,'bone_setup'):
            compose_scene(base,[dict(source_layer_id='arm',documents=[donor])],source,skeleton)
        donor['bones'][0]['x']=0
        other=deepcopy(donor);other['animations']={'unsupported':{}}
        with self.assertRaisesRegex(ValueError,'motion_inventory'):
            compose_scene(base,[dict(source_layer_id='arm',documents=[donor,other])],source,skeleton)

    def test_duplicate_regions_and_unknown_sources_fail(self):
        base, donor, source, skeleton=fixture()
        for changes,reason in [([dict(source_layer_id='arm',documents=[donor,donor])],'duplicate_region'),
                               ([dict(source_layer_id='missing',documents=[donor])],'source_not_directly')]:
            with self.assertRaisesRegex(ValueError,reason): compose_scene(base,changes,source,skeleton)

    def test_helper_indices_are_remapped_without_changing_setup(self):
        base, donor, source, skeleton=fixture()
        base['bones'].append(dict(name='unrelated',parent='root',x=1,y=0,rotation=0,length=1))
        donor['bones'].append(dict(name='helper',parent='root',x=2,y=0,rotation=0,length=1))
        values=donor['skins'][0]['attachments']['part']['part']['vertices']
        for index in (1,6,11):values[index]=1
        doc,_=compose_scene(base,[dict(source_layer_id='arm',documents=[donor])],source,skeleton)
        self.assertEqual(doc['bones'][-1],donor['bones'][-1])
        remapped=doc['skins'][0]['attachments']['part']['part']['vertices']
        self.assertEqual([remapped[i] for i in (1,6,11)],[2,2,2])

    def test_rgba_subtraction_retains_residual_and_rejects_double_ownership(self):
        from PIL import Image
        def encode(pixels):
            image=Image.new('RGBA',(2,1));image.putdata(pixels);out=BytesIO();image.save(out,format='PNG');return out.getvalue()
        original=encode([(20,30,40,255),(40,50,60,7)])
        part=encode([(20,30,40,255),(0,0,0,0)])
        residual,count,size=subtract_components(original,[part])
        self.assertEqual((count,size),(1,(2,1)))
        with Image.open(BytesIO(residual)) as image: self.assertEqual(image.getpixel((1,0)),(40,50,60,7))
        with self.assertRaisesRegex(ValueError,'overlap'): subtract_components(original,[part,part])
        with self.assertRaisesRegex(ValueError,'not_source_subset'):
            subtract_components(original,[encode([(21,30,40,255),(0,0,0,0)])])
