from copy import deepcopy
import unittest
from autospine_workbench.targets.spine43.seam_stable_fallback import build


class FallbackTests(unittest.TestCase):
    def fixture(self):
        animation={'bones':{},'attachments':{'default':{n:{n:{'deform':[{'time':0,'vertices':[0,0]},{'time':1,'vertices':[i,2]},{'time':2,'vertices':[0,0]}]}} for i,n in enumerate(('left','right'))}}}
        source={'bones':[],'slots':[],'skins':[],'animations':{'reference':animation}}
        candidate=deepcopy(source);candidate['animations']={'candidate':deepcopy(animation)}
        for row in candidate['animations']['candidate']['attachments']['default'].values():
            next(iter(row.values()))['deform'][1]['vertices']=[5,6]
        return source,candidate

    def test_whole_track_restore_and_other_side_preserved(self):
        reference,candidate=self.fixture();saved=deepcopy(candidate)
        result=build(reference,candidate,['left'])
        tracks=result['animations']['candidate']['attachments']['default']
        self.assertEqual(tracks['left'],reference['animations']['reference']['attachments']['default']['left'])
        self.assertEqual(tracks['right'],candidate['animations']['candidate']['attachments']['default']['right'])
        self.assertEqual(candidate,saved)
        self.assertEqual(build(reference,result,['left']),result)

    def test_mismatched_source_and_missing_selection_fail(self):
        reference,candidate=self.fixture()
        with self.assertRaises(ValueError):build(reference,candidate,['missing'])
        with self.assertRaises(ValueError):build(reference,candidate,['left','left'])
        reference['bones']=[{}]
        with self.assertRaises(ValueError):build(reference,candidate,['left'])
