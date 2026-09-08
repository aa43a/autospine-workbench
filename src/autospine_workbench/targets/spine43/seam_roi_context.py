"""Local framebuffer topology: reaching a crop edge never proves global exterior."""
import math


def analyze(before, after, center, connectivity=4):
    if connectivity not in (4,8):
        raise ValueError('roi_connectivity')
    height = len(before)
    width = len(before[0]) if height else 0
    if not width or len(after) != height or any(len(r) != width for r in before+after):
        raise ValueError('roi_shape')
    if any(type(v) is not int or not 0 <= v <= 255 for row in before+after for v in row):
        raise ValueError('roi_alpha')
    x, y = center
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError('roi_center')
    transparent = {(x, y) for y in range(height) for x in range(width) if after[y][x] < 8}
    introduced = {(x, y) for x, y in transparent if before[y][x] >= 8}
    remaining = set(transparent)
    regions = []
    while remaining:
        start = min(remaining, key=lambda p: (p[1], p[0]))
        remaining.remove(start)
        component, queue = {start}, [start]
        while queue:
            px, py = queue.pop()
            neighbors = [(px-1, py), (px+1, py), (px, py-1), (px, py+1)]
            if connectivity == 8:
                neighbors += [(px+dx,py+dy) for dx in (-1,1) for dy in (-1,1)]
            for point in neighbors:
                if point in remaining:
                    remaining.remove(point); component.add(point); queue.append(point)
        new = component & introduced
        if new:
            rim = any(px in (0, width-1) or py in (0, height-1) for px, py in component)
            regions.append(dict(context='reaches_roi_edge' if rim else 'enclosed_in_roi',
                                new_pixels=[list(p) for p in sorted(new, key=lambda p: (p[1], p[0]))]))
    return dict(center_before_alpha=before[y][x], center_after_alpha=after[y][x],
                center_after_below8=after[y][x]<8,
                center_distance_to_low_alpha_px=min((math.dist(center, p) for p in transparent), default=None),
                new_low_alpha_pixels=len(introduced),
                regained_pixels=sum(before[py][px]<8<=after[py][px] for py in range(height) for px in range(width)),
                components=regions)
