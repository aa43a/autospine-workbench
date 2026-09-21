from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image

from autospine_workbench.targets.character43.motion_depth_overlap import Probe, inspect, RasterBudgetError


def fixture(transparent=False):
    mesh = dict(type='mesh', uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3],
                vertices=[1, 0, 0, 2, 1, 1, 0, 2, 2, 1, 1, 0, 2, 0, 1, 1, 0, 0, 0, 1])
    doc = dict(bones=[dict(name='root', x=0, y=0, rotation=0)],
        slots=[dict(name=n, bone='root', attachment=n) for n in ('a', 'b')],
        skins=[dict(attachments={n: {n: dict(mesh)} for n in ('a', 'b')})], animations={'test': {'bones': {}}})
    files = {}
    for name in ('a', 'b'):
        out = BytesIO(); Image.new('RGBA', (2, 2), (255, 255, 255, 0 if transparent and name == 'b' else 255)).save(out, format='PNG')
        files['images/'+name+'.png'] = out.getvalue()
    return doc, files


class DepthOverlapTests(unittest.TestCase):
    def test_inspection_keeps_budget_location_and_does_not_fabricate_overlap(self):
        doc,files=fixture()
        depth=dict(pairs=[dict(arm_slot='a',torso_slot='b',samples=[dict(tick=0)])])
        error=RasterBudgetError('a','b',0,[0,0,2,2],1)
        with patch.object(Probe,'pair',side_effect=error):
            report,_=inspect(doc,files,'test',depth)
        sample=report['pairs'][0]['samples'][0]['overlap']
        self.assertEqual(sample['status'],'unmeasured')
        self.assertEqual(sample['raster_budget']['required_pixels'],8)
        self.assertNotIn('overlap_pixels',sample)
        self.assertEqual(report['target_overlap']['unmeasured_pair_samples'],1)

    def test_completed_cache_reuse_preserves_budget_and_checks_identity(self):
        doc,files=fixture(); source=Probe(doc,files,'test'); target=Probe(doc,files,'test')
        source.pair('a','b',0)
        self.assertEqual(target.reuse(source),1)
        self.assertEqual(target.reuse(source),0)
        self.assertEqual(target.pair('b','a',0)['overlap_pixels'],4)
        self.assertEqual(target.remaining,64_000_000)
        source.results['a','b',0]['overlap_pixels']=3
        self.assertEqual(target.results['a','b',0]['overlap_pixels'],4)
        with self.assertRaisesRegex(ValueError,'cache_conflict'): target.reuse(source)
        with self.assertRaisesRegex(ValueError,'cache_identity'):
            target.reuse(Probe(doc,files,'test',rendered_bounds=True))
        with self.assertRaisesRegex(ValueError,'cache_identity'):
            target.reuse(Probe(dict(doc),files,'test'))

    def test_rendered_bounds_exclude_unused_vertices_without_changing_overlap(self):
        doc,files=fixture()
        for name in ('a','b'):
            mesh=doc['skins'][0]['attachments'][name][name]
            mesh['vertices']=mesh['vertices']+[1,0,100,100,1]
            mesh['uvs']=mesh['uvs']+[0,0]
        legacy=Probe(doc,files,'test'); clipped=Probe(doc,files,'test',rendered_bounds=True)
        self.assertEqual(legacy.pair('a','b',0)['overlap_pixels'],clipped.pair('a','b',0)['overlap_pixels'])
        self.assertEqual(clipped.pair('a','b',0)['roi'],[0,-2,2,2])
        self.assertGreater(clipped.remaining,legacy.remaining)
        self.assertEqual(Probe(doc,files,'test',pixel_budget=8,rendered_bounds=True).pair('a','b',0)['overlap_pixels'],4)
        with self.assertRaisesRegex(ValueError,'pixel_budget'):
            Probe(doc,files,'test',pixel_budget=8).pair('a','b',0)

    def test_rendered_bounds_reject_invalid_indices_and_allow_empty_mesh(self):
        doc,files=fixture(); mesh=doc['skins'][0]['attachments']['a']['a']
        mesh['triangles']=[0,1,-1]
        with self.assertRaisesRegex(ValueError,'triangle_indices_invalid'):
            Probe(doc,files,'test',rendered_bounds=True).pair('a','b',0)
        mesh['triangles']=[]
        self.assertEqual(Probe(doc,files,'test',rendered_bounds=True).pair('a','b',0)['overlap_pixels'],0)

    def test_exact_mesh_overlap_uses_alpha_and_world_y_flip(self):
        doc, files = fixture()
        result = Probe(doc, files, 'test').pair('a', 'b', 0)
        self.assertEqual(result['overlap_pixels'], 4)
        self.assertEqual(result['roi'], [0, -2, 2, 2])
        doc, files = fixture(True)
        self.assertEqual(Probe(doc, files, 'test').pair('a', 'b', 0)['overlap_pixels'], 0)

    def test_budget_failure_is_not_absence_of_overlap(self):
        doc, files = fixture()
        with self.assertRaisesRegex(ValueError, 'pixel_budget') as caught:
            Probe(doc, files, 'test', pixel_budget=1).pair('a', 'b', 0)
        self.assertEqual(caught.exception.diagnostic['limit_kind'],'aggregate_budget')
        self.assertEqual(caught.exception.diagnostic['required_pixels'],8)
        doc['animations']['test']['slots'] = {'a': {'rgba': []}}
        with self.assertRaisesRegex(ValueError, 'attachment_unsupported'):
            Probe(doc, files, 'test').pair('a', 'b', 0)

    def test_visible_mismatch_is_separate_from_ambiguous_depth(self):
        doc, files = fixture()
        depth = dict(pairs=[dict(arm_slot='a', torso_slot='b', setup_front_slot='b', samples=[
            dict(tick=0, ambiguous=False, current_front_slot='a'),
            dict(tick=1000, ambiguous=True, current_front_slot='a')])])
        report, _ = inspect(doc, files, 'test', depth)
        self.assertEqual(report['target_overlap']['order_mismatch_pair_samples'], 1)
        self.assertEqual(report['target_overlap']['ambiguous_visible_pair_samples'], 1)
        self.assertNotIn('overlap', depth['pairs'][0]['samples'][0])


if __name__ == '__main__':
    unittest.main()
