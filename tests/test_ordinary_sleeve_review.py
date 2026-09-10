import json
import unittest

from autospine_workbench.asset.planning.ordinary_sleeve_review import render


class OrdinarySleeveReviewTests(unittest.TestCase):
    def source(self):
        return dict(schema='autospine.ordinary-sleeve-motion/v1', project_id='ordinary-test', authority='none',
                    production_authorized=False, records=[])

    def test_residual_rows_are_retained_with_reason_and_no_success_claim(self):
        source = self.source()
        source['records'] = [dict(layer_id='residual-layer', component_id='remaining', status='blocked',
                                 reason_codes=['ordinary_sleeve_region_unavailable'])]
        page = render(source)
        self.assertIn('residual-layer / remaining', page)
        self.assertIn('无有效动作轨道', page)
        self.assertIn('未绘制源纹理', page)
        self.assertIn('不代表正式采用或最终 Runtime', page)

    def test_payload_escapes_script_and_geometry_stays_read_only(self):
        source = self.source()
        source['project_id'] = '<script>project</script>'
        source['records'] = [dict(layer_id='<script>layer</script>', component_id='part', status='blocked',
            reason_codes=['motion_envelope_geometry_failure'], setup_vertices=[[0, 0]], triangles=[],
            tracks=[dict(bone_id='</script><script>alert(1)</script>', samples=[dict(tick=0, points=[[0, 0]])], qa=[{}])])]
        page = render(source)
        self.assertNotIn('<script>project</script>', page)
        encoded = page.split('<script type="application/json" id="data">')[1].split('</script>')[0]
        self.assertNotIn('</script>', encoded)
        self.assertEqual(json.loads(encoded)[0]['tracks'][0]['bone_id'], source['records'][0]['tracks'][0]['bone_id'])
        self.assertIn('type="range"', page)
        self.assertNotIn('fetch(', page)
        self.assertNotIn('下载', page)

    def test_rejects_authority_and_nonfinite_data(self):
        source = self.source()
        source['authority'] = 'approved'
        with self.assertRaises(ValueError): render(source)
        source = self.source()
        source['records'] = [dict(layer_id='a', component_id='b', status='blocked', setup_error=float('nan'))]
        with self.assertRaises(ValueError): render(source)


if __name__ == '__main__':
    unittest.main()
