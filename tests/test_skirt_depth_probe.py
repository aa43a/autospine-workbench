import unittest
from autospine_workbench.targets.character43.skirt_depth_probe import groups,inspect


class SkirtProbeTests(unittest.TestCase):
    def document(self):
        return dict(bones=[dict(name='thigh_l'),dict(name='arbitrary-layer-skirt_0_upper'),dict(name='head')],
            slots=[dict(name=n,attachment=n) for n in ('leg','cloth','accessory')],
            skins=[dict(attachments={n:{n:dict(type='mesh',uvs=[0,0],vertices=[1,i,0,0,1])}
                for i,n in enumerate(('leg','cloth','accessory'))})])
    def test_groups_follow_weighted_influences(self):
        self.assertEqual(groups(self.document()),(['leg'],['cloth']))
    def test_missing_legs_are_not_a_pass(self):
        doc=self.document();doc['slots']=doc['slots'][1:]
        result=inspect(doc,{},None,[0])
        self.assertEqual(result['status'],'unmeasured')
        self.assertFalse(result['order_changed'])
    def test_invalid_bone_index_rejected(self):
        doc=self.document();doc['skins'][0]['attachments']['leg']['leg']['vertices'][1]=99
        with self.assertRaisesRegex(ValueError,'bone_invalid'):groups(doc)


if __name__=='__main__':unittest.main()
