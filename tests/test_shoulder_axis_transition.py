import copy
import unittest
from autospine_workbench.targets.character43.shoulder_axis_transition import propose


def fixture():
    bones=[dict(name='chest',x=20,y=30,rotation=25),
           dict(name='upperarm_l',parent='chest',x=2,y=3,rotation=-60),
           dict(name='forearm_l',parent='upperarm_l',x=10,y=0,rotation=0)]
    mesh=dict(type='mesh',uvs=[0,0,0,1,1,0],triangles=[0,1,2],
              vertices=[1,1,1,0,1,1,1,2,2,1,1,1,8,0,1])
    return dict(bones=bones,slots=[dict(name='arm',attachment='arm',bone='upperarm_l')],
                skins=[dict(attachments={'arm':{'arm':mesh}})],animations={'motion':{'bones':{}}})


class ShoulderTransitionTests(unittest.TestCase):
    def test_setup_preserved_and_distal_untouched(self):
        doc=fixture();before=copy.deepcopy(doc);result,report=propose(doc)
        self.assertEqual(doc,before)
        self.assertLess(report['setup_max_error_px'],1e-10)
        self.assertEqual([r['vertex'] for r in report['records'][0]['changed']],[0,1])
        self.assertEqual(result['skins'][0]['attachments']['arm']['arm']['vertices'][-5:],
                         doc['skins'][0]['attachments']['arm']['arm']['vertices'][-5:])
        self.assertEqual(result['animations'],doc['animations'])

    def test_existing_deform_cannot_be_reinterpreted(self):
        doc=fixture();doc['animations']['motion']['attachments']={'default':{'arm':{'arm':{'deform':[]}}}}
        with self.assertRaisesRegex(ValueError,'existing_deform'):propose(doc)

    def test_no_unbounded_transition(self):
        for value in (0,1,float('nan')):
            with self.assertRaisesRegex(ValueError,'band_invalid'):propose(fixture(),band_ratio=value)
