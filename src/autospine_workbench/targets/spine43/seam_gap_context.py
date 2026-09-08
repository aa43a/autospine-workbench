"""Conservative local support evidence; never a crack or adoption classifier."""
import numpy as np


def classify(driver, follower, added, radius=4):
    """Inspect bounded opposite rays. Outside the ROI is unknown, never background."""
    if radius != 4:
        raise ValueError('gap_context_profile_radius')
    arrays = [np.asarray(x) for x in (driver, follower, added)]
    if any(x.dtype != bool or x.ndim != 2 for x in arrays):
        raise ValueError('gap_context_boolean_masks')
    if any(x.shape != arrays[0].shape for x in arrays):
        raise ValueError('gap_context_shape')
    driver, follower, added = arrays
    if np.any(added & (driver | follower)):
        raise ValueError('gap_context_occupied_gap')
    height, width = added.shape
    labels = np.zeros(added.shape, dtype=np.uint8)
    for y, x in np.argwhere(added):
        opposed = False
        supports = set()
        clipped = False
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            sides = []
            for sign in (-1, 1):
                hit = 0
                for step in range(1, radius + 1):
                    yy, xx = y + sign * dy * step, x + sign * dx * step
                    if not (0 <= yy < height and 0 <= xx < width):
                        clipped = True
                        break
                    hit = int(driver[yy, xx]) + 2 * int(follower[yy, xx])
                    if hit:
                        supports.add(hit)
                        break
                sides.append(hit)
            # Overlap is not exclusive evidence of two opposing surfaces.
            opposed |= sides in ([1, 2], [2, 1])
        labels[y, x] = 1 if opposed else 2 if not clipped and supports in ({1}, {2}) else 3
    counts = {name: int((labels == index).sum()) for index, name in enumerate(
        ('opposed_attachment_support', 'single_attachment_support', 'uncertain'), 1)}
    assert sum(counts.values()) == int(added.sum())
    return counts, labels
