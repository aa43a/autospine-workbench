import random
import unittest
from autospine_workbench.targets.character43.motion_depth_order import _sort


def previous(slots,edges):
    remaining=set(slots);output=[]
    while remaining:
        candidate=next((s for s in slots if s in remaining and
            not any(b==s and a in remaining for a,b in edges)),None)
        if candidate is None:return None
        output.append(candidate);remaining.remove(candidate)
    return output


class StableOrderSortTests(unittest.TestCase):
    def test_priority_and_cycles_match_existing_sort(self):
        rng=random.Random(27)
        for count in [1,3,10,40]:
            slots=[f's{i}' for i in range(count)]
            for _ in range(20):
                edges={(a,b) for a in slots for b in slots if rng.random()<.08}
                self.assertEqual(_sort(slots,edges),previous(slots,edges))
                order=slots.copy();rng.shuffle(order)
                edges={(a,b) for i,a in enumerate(order) for b in order[i+1:] if rng.random()<.2}
                self.assertEqual(_sort(slots,edges),previous(slots,edges))


if __name__=='__main__':unittest.main()
