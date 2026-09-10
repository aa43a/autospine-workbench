"""Absolute harmonic hand influence on reviewed cuff vertices, without geometry edits."""
from copy import deepcopy
import math

PROFILE = 'ordinary-cuff-absolute-harmonic-jacobi128-v1'
ITERATIONS = 128
ROLES = {'hand', 'sleeve', 'cuff', 'unknown', 'hanging_cloth'}


def reweight(mesh, assignments):
    """Three influences retain their local coordinates and order.

    The third influence is hand; the second is forearm. Hand/unknown vertices
    retain their exact original rows. Only pure sleeve and reviewed cuff domains
    can change; unrepresented and unsupported domains remain untouched.
    """
    count = len(mesh['vertices_xy'])
    if len(mesh['weights']) != count or len(assignments) != len(mesh['triangles']):
        raise ValueError('ordinary_cuff_inventory')
    bones = mesh['bone_ids']
    if len(bones) != 3 or len(set(bones)) != 3:
        raise ValueError('ordinary_cuff_three_bones_required')
    original = []
    for row in mesh['weights']:
        if [entry['bone_id'] for entry in row] != bones:
            raise ValueError('ordinary_cuff_bone_order')
        values = [entry['weight'] for entry in row]
        if (any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w)
                or not 0 <= w <= 1 for w in values) or abs(sum(values)-1) > 1e-9):
            raise ValueError('ordinary_cuff_weights_invalid')
        original.append(values[2])
    roles = [set() for _ in range(count)]
    neighbors = [set() for _ in range(count)]
    for index, (triangle, item) in enumerate(zip(mesh['triangles'], assignments)):
        if (len(triangle) != 3 or len(set(triangle)) != 3
                or any(type(i) is not int or not 0 <= i < count for i in triangle)):
            raise ValueError('ordinary_cuff_triangle_invalid')
        if item.get('triangle_id', index) != index or item.get('role') not in ROLES:
            raise ValueError('ordinary_cuff_assignment_invalid')
        for i in triangle:
            roles[i].add(item['role'])
            neighbors[i].update(j for j in triangle if j != i)
    values = original[:]
    free, zero, protected, hand = [], [], [], []
    for i, domain in enumerate(roles):
        if not domain or 'unknown' in domain:
            protected.append(i)
        elif 'hand' in domain:
            hand.append(i)
        elif domain == {'sleeve'}:
            zero.append(i); values[i] = 0.
        elif 'cuff' in domain and domain <= {'sleeve', 'cuff'}:
            free.append(i)
        else:
            protected.append(i)
    adjacent = {i: sorted(neighbors[i]) for i in free}
    for _ in range(ITERATIONS):
        updated = values[:]
        for i in free:
            if adjacent[i]:
                updated[i] = sum(values[j] for j in adjacent[i])/len(adjacent[i])
        values = updated
    result = deepcopy(mesh)
    for i in free + zero:
        row = result['weights'][i]
        target = values[i]
        # Absolute hand influence may increase from zero. This deliberately
        # differs from multiplying the previous hand influence by a ratio.
        if target == original[i]: continue
        remainder = 1.-target
        nonhand = row[0]['weight']+row[1]['weight']
        upper = remainder*row[0]['weight']/nonhand if nonhand else 0.
        row[0]['weight'], row[1]['weight'], row[2]['weight'] = upper, remainder-upper, target
    changed = [i for i, (a, b) in enumerate(zip(mesh['weights'], result['weights'])) if a != b]
    return result, dict(profile=PROFILE, iterations=ITERATIONS, free_vertices=free,
        zero_hand_vertices=zero, pinned_hand_vertices=hand, protected_vertices=protected,
        changed_vertices=changed, hand_influence_before=original, hand_influence_after=values,
        authority='none', production_authorized=False)
