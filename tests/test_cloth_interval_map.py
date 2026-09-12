from copy import deepcopy
import unittest
import importlib.util
from autospine_workbench.targets.character43.cloth_interval_map import build
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.deform_sum import combine


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional numerical solver')
class IntervalMapTests(unittest.TestCase):
    def test_matches_actual_blended_spine_deform_with_intermediate_original_keys(self):
        import numpy as np
        old = [dict(time=0, vertices=[0.]*4), dict(time=.3, vertices=[.2, -.1]*2),
               dict(time=1, vertices=[0.]*4)]
        doc = dict(bones=[dict(name='arm', x=3., y=4., rotation=5.),
            dict(name='cloth', parent='arm', x=2., y=0., rotation=-15.)],
            skins=[dict(attachments={'fabric': {'fabric': dict(vertices=[2, 0, 1., 1., .3, 1, 2., 1., .7])}})],
            animations={'wave': dict(bones={
                'arm': {'rotate': [dict(time=0, value=0), dict(time=1, value=90)]},
                'cloth': {'rotate': [dict(time=0, value=0), dict(time=1, value=-70)]}},
                attachments={'default': {'fabric': {'fabric': {'deform': old}}}})})
        left = np.asarray(sample(doc, 'wave', 0)[0]['fabric'])+[[1., -2.]]
        right = np.asarray(sample(doc, 'wave', 1)[0]['fabric'])+[[3., 4.]]
        maps = build(doc, 'wave', 'fabric', 0., 1., left)
        keys = []
        for time, points in [(0., left), (1., right)]:
            delta = points[0]-np.asarray(sample(doc, 'wave', time)[0]['fabric'][0]); offsets = []
            for name in ('arm', 'cloth'):
                a, b, c, d, _, _ = matrices(doc, 'wave', time)[name]
                offsets.extend(np.linalg.solve([[a, b], [c, d]], delta).tolist())
            keys.append(dict(time=time, vertices=offsets))
        trial = deepcopy(doc)
        trial['animations']['wave']['attachments']['default']['fabric']['fabric']['deform'] = combine(old, keys)
        for time, (bias, transform) in zip((.25, .5, .75), maps):
            expected = sample(trial, 'wave', time)[0]['fabric']
            actual = bias+np.einsum('nij,nj->ni', transform, right)
            np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=0)
