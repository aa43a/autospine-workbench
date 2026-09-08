"""Deterministic eight-connected components and conservative adjacent-tick tracks."""
import math


def components(labels, rect, tick):
    pending = {(int(y), int(x)) for y, x in zip(*labels.nonzero())}
    result = []
    while pending:
        seed = min(pending); pending.remove(seed); todo = [seed]; pixels = []
        while todo:
            y, x = todo.pop(); pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    point = (y + dy, x + dx)
                    if point in pending:
                        pending.remove(point); todo.append(point)
        pixels.sort()
        points = [[rect[0] + x + .5, -(rect[1] + y + .5)] for y, x in pixels]
        xs, ys = zip(*points)
        result.append(dict(id=f'f{tick}-c{len(result)}', frame=tick, area_px=len(points),
                           pixels_world=points, centroid=[sum(xs)/len(xs), sum(ys)/len(ys)],
                           bbox=[min(xs)-.5, min(ys)-.5, max(xs)+.5, max(ys)+.5],
                           support_counts=[sum(int(labels[y, x]) == k for y, x in pixels) for k in (1, 2, 3)]))
    return result


def associate(frames, *, distance_fn=None):
    """Only mutual unique neighbors within 3 world pixels extend a track.

    Splits/merges are candidate graph events, not asserted physical identities.
    Empty frames break tracks; no loop closure or occlusion bridging is inferred.
    """
    tracks = []; assignments = {}; events = []; previous = []
    for tick, current in enumerate(frames):
        if any(c['frame'] != tick for c in current):
            raise ValueError('gap_track_frame_sequence')
        edges = []
        for a in previous:
            for b in current:
                distance = (distance_fn(a, b) if distance_fn is not None else
                            min(math.dist(p, q) for p in a['pixels_world'] for q in b['pixels_world']))
                if distance is not None and distance <= 3:
                    edges.append((a['id'], b['id'], distance))
        outgoing = {a['id']: [e for e in edges if e[0] == a['id']] for a in previous}
        incoming = {b['id']: [e for e in edges if e[1] == b['id']] for b in current}
        for source, candidates in outgoing.items():
            if len(candidates) > 1:
                events.append(dict(frame=tick, kind='split_candidate', source=source, targets=[e[1] for e in candidates]))
        for b in current:
            candidates = incoming[b['id']]
            if len(candidates) > 1:
                events.append(dict(frame=tick, kind='merge_candidate', target=b['id'], sources=[e[0] for e in candidates]))
            if len(candidates) == 1 and len(outgoing[candidates[0][0]]) == 1:
                index = assignments[candidates[0][0]]
            else:
                index = len(tracks); tracks.append(dict(id=f'track-{index}', components=[]))
            assignments[b['id']] = index; tracks[index]['components'].append(b)
        previous = current
    for track in tracks:
        items = track['components']; areas = [c['area_px'] for c in items]
        track.update(start_frame=items[0]['frame'], end_frame=items[-1]['frame'],
                     observed_frames=len(items), max_area_px=max(areas), mean_area_px=sum(areas)/len(areas),
                     classification='unclassified', status='needs_review')
    return dict(tracks=tracks, association_events=events,
                pixel_samples=sum(c['area_px'] for f in frames for c in f))
