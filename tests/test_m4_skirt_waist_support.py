import unittest
from unittest.mock import patch
from PIL import Image
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_skirt_waist_support import fixed_region,contact_change


class WaistSupportTests(unittest.TestCase):
    def files(self):
        mesh={'triangles':[0,1,2,1,3,2]}
        doc={'bones':[],'slots':[],'skins':[{'attachments':{'skirt':{'skirt':mesh},'torso':{'torso':mesh}}}]}
        return {'skeleton.json':canonical_bytes(doc),
            'skirt-trial.json':canonical_bytes({'rows':[{'layer_id':'skirt','origin':[0,0],
                'contact':{'waist_y':1,'overlap_x':[2,8]}}]}),
            'character-manifest.json':canonical_bytes({'layers':[{'name':'topwear','state':'rigid_reviewed',
                'regions':[{'region_id':'torso'}]}]})}

    def test_fixed_region_comes_from_contact_triangles(self):
        files=self.files();points=[[0,0],[20,0],[0,-20],[20,-20]]
        with patch('m4_skirt_waist_support.sample',return_value=({'skirt':points,'torso':points},{})),patch('m4_skirt_waist_support.source_image',return_value=(Image.new('RGBA',(20,20),(255,255,255,255)),[0,0])):
            fixed,evidence=fixed_region(files,files,'skirt')
        self.assertEqual(fixed,[0,1,2])
        changed=[p[:] for p in points];changed[3]=[25,-25]
        self.assertEqual(contact_change(points,changed,evidence['anchors']),0)
        changed[0][0]+=1
        self.assertGreater(contact_change(points,changed,evidence['anchors']),0)

    def test_changed_bind_structure_rejects_reused_contact(self):
        files=self.files();changed=dict(files,skeleton_json=b'{}')
        changed['skeleton.json']=canonical_bytes({'bones':[{'name':'other'}]})
        with self.assertRaisesRegex(ValueError,'bind_mismatch'):fixed_region(files,changed,'skirt')


if __name__=='__main__':unittest.main()
