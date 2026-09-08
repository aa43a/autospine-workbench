"""4.3 region UVs, texture identities, and reflected weighted setup encoding."""
from copy import deepcopy
import hashlib
import json
import math
import unittest
from tests.test_shared_partitions import inputs
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.shared_partitions import combine_layer
from autospine_workbench.asset.joints.ownership_atlas import build
from autospine_workbench.asset.joints.mesh_weights import _rotate
from autospine_workbench.targets.spine43.ownership_preview import build_preview,region_uvs
from autospine_workbench.resolved_project import canonical_sha256


def source():
    args=inputs();shared=combine_layer(*args);layer,page=build(args[0],args[1],shared)
    bones=[{'id':'pelvis','parent_id':None,'head_xy':[0,0],'world_rotation_degrees':0,'length':0,
            'setup_local':{'x':0,'y':0,'rotation_degrees':0}}]
    for side in ('l','r'):
        for b in deepcopy(fixture()[-1]['bones']):
            b['id']=b['id'].replace('_l','_'+side);b['parent_id']=b['parent_id'].replace('_l','_'+side)
            parent=next(p for p in bones if p['id']==b['parent_id']);local=_rotate([b['head_xy'][k]-parent['head_xy'][k] for k in (0,1)],-parent['world_rotation_degrees'])
            b['setup_local']={'x':local[0],'y':local[1],'rotation_degrees':b['world_rotation_degrees']-parent['world_rotation_degrees']}
            b['length']=math.dist(b['head_xy'],b['tail_xy']);bones.append(b)
    skeleton={'bones':bones,'canvas':[150,300]}
    atlas={'schema':'autospine.ownership-atlas/v1','source_skeleton_sha256':canonical_sha256(skeleton),
           'layers':[layer],'files':{layer['page_ref']:hashlib.sha256(page).hexdigest()}}
    return atlas,skeleton,{layer['page_ref']:page}


class OwnershipTargetTests(unittest.TestCase):
    def test_encoding_uv_roundtrip_setup_and_editor_paths(self):
        args=source();before=deepcopy(args);scope,files=build_preview(*args)
        self.assertEqual(args,before);self.assertEqual((scope,files),build_preview(*args))
        doc=json.loads(files['skeleton.json']);self.assertEqual(doc['skeleton']['spine'],'4.3.26')
        self.assertEqual(json.loads(files['editor/skeleton.json'])['skeleton']['images'],'./images/')
        frames={}
        for b in doc['bones']:
            head,rotation=frames.get(b.get('parent'),([0,0],0))
            offset=_rotate([b['x'],b['y']],rotation)
            frames[b['name']]=([head[k]+offset[k] for k in (0,1)],rotation+b['rotation'])
        for r in scope['regions']:
            a=doc['skins'][0]['attachments'][r['id']][r['id']];vertices=a['vertices'];i=0;positions=[]
            while i<len(vertices):
                count=vertices[i];i+=1;p=[0.,0.]
                for _ in range(count):
                    index,x,y,weight=vertices[i:i+4];i+=4
                    head,rot=frames[doc['bones'][index]['name']];xy=_rotate([x,y],rot)
                    for k in (0,1):p[k]+=(head[k]+xy[k])*weight
                positions.append([p[0],-p[1]])
            for a,b in zip(positions,r['setup_vertices_xy']):self.assertLess(math.dist(a,b),1e-7)
            self.assertIn('editor/images/'+r['id']+'.png',files)
            self.assertLess(r['source_uv_max_error'],1e-9)
        self.assertFalse(scope['production_authorized'])
        self.assertTrue(all(r['status']=='excluded_unbound' for r in scope['residuals']))

    def test_invalid_sources_sampler_and_uv_fail_closed(self):
        args=source();args[0]['source_skeleton_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source_mismatch'):build_preview(*args)
        args=source();args[0]['layers'][0]['sampler']['mipmaps']=True
        with self.assertRaisesRegex(ValueError,'sampler_unsupported'):build_preview(*args)
        args=source();args[2][next(iter(args[2]))]=b'changed'
        with self.assertRaisesRegex(ValueError,'page_changed'):build_preview(*args)
        for uv in ([[float('nan'),0]],[[2,0]]):
            with self.assertRaisesRegex(ValueError,'uv_invalid'):region_uvs(uv,(100,100),(2,2,24,80))
