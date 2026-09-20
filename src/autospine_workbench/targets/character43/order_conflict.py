"""Deterministic, bounded cycle witnesses for back-to-front constraints."""


def witness(slots, evidence):
    adjacency = {slot: [] for slot in slots}
    for back, front in sorted(evidence):
        adjacency[back].append(front)
    done = set()
    for root in slots:
        if root in done:
            continue
        path = [root]
        active = {root: 0}
        stack = [iter(adjacency[root])]
        while stack:
            node = next(stack[-1], None)
            if node is None:
                stack.pop()
                done.add(path[-1])
                active.pop(path.pop())
            elif node in active:
                cycle = path[active[node]:] + [node]
                return dict(slots=cycle, edges=[
                    dict(back=a, front=b, **evidence[a, b])
                    for a, b in zip(cycle, cycle[1:])])
            elif node not in done:
                active[node] = len(path)
                path.append(node)
                stack.append(iter(adjacency[node]))
    return None


def first_overlap(probe, a, b, times):
    """Keep the actual positive sample; do not claim unsampled times passed."""
    for time in times:
        pixels = probe.pair(a, b, time)['overlap_pixels']
        if pixels:
            return dict(time=time, overlap_pixels=pixels)
    return None
