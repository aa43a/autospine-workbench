import unittest
import math
from autospine_workbench.targets.character43.alpha_contact_disks import disks


class DiskTests(unittest.TestCase):
    def test_disk_does_not_bridge_alpha_hole(self):
        pixels=[(x,y) for x in range(15) for y in range(15) if not 5<=x<=9 or not 5<=y<=9]
        disk=disks(pixels,[[7,4]],4)[0]
        for x,y in [(x,y) for x in range(5,10) for y in range(5,10)]:
            self.assertGreater(math.dist(disk['center'],[x,y]),disk['radius'])

    def test_thin_support_does_not_invent_contact_area(self):
        with self.assertRaisesRegex(ValueError,'no_supported_interior'):disks([(x,0) for x in range(10)],[[3,0]],4)
