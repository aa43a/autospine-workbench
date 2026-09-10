"""Bounded four-connected alpha evidence compatible with the original PSD audit."""


def alpha_statistics(image):
    alpha = image.getchannel('A')
    histogram = alpha.histogram()
    nonzero, perceptible = sum(histogram[1:]), sum(histogram[8:])
    data = alpha.tobytes()
    parents, areas, previous = [], [], []

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for y in range(image.height):
        current = []
        x = 0
        while x < image.width:
            if data[y * image.width + x] < 8:
                x += 1
                continue
            start = x
            while x < image.width and data[y * image.width + x] >= 8:
                x += 1
            if len(parents) >= 1_048_576:
                from .psd_intake_worker import PsdIntakeError
                raise PsdIntakeError('psd_alpha_limit', 'Layer alpha exceeds run metadata limit')
            label = len(parents)
            parents.append(label)
            areas.append(x - start)
            current.append((start, x, label))
        cursor = 0
        for start, end, label in current:
            while cursor < len(previous) and previous[cursor][1] <= start:
                cursor += 1
            scan = cursor
            while scan < len(previous) and previous[scan][0] < end:
                a, b = root(label), root(previous[scan][2])
                if a != b:
                    parents[b] = a
                    areas[a] += areas[b]
                scan += 1
        previous = current
    components = sorted((areas[i] for i in range(len(parents)) if root(i) == i), reverse=True)
    return dict(alpha_nonzero=nonzero, alpha_perceptible=perceptible,
                alpha_opaque=sum(histogram[128:]), alpha_low_1_7=sum(histogram[1:8]),
                component_count=len(components), component_areas_top5=components[:5],
                main_component_ratio=round(components[0] / perceptible, 6) if perceptible else 0,
                empty=not nonzero, fills_bbox_ratio=round(nonzero / (image.width * image.height), 6))
