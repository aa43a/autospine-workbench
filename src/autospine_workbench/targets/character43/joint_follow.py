"""Conservative secondary-motion discovery and rigid pendulum conversion.

Own Spine implementation; no dependency on the upstream WebGL renderer.
Only an already single-bone weighted mesh can become a rigid follower.
"""
from .joint_secondary_mesh import _rows
import math


HAIR_NAMES = {'back hair', 'front hair', 'side hair', 'hair', 'hair front', 'hair back',
              '前髪', '後ろ髪', '横髪', '前发', '后发', '侧发'}
OBJECT_NAMES = {'objects', 'object', 'accessory', 'accessories', 'earring', 'earrings',
                'tail', 'ribbon', 'ribbons', 'neckwear', '物件', '饰品', '耳饰', '尾巴', '飘带'}


def semantic(name):
    return ' '.join(str(name).strip().lower().replace('_', ' ').replace('-', ' ').split())


def rigid_driver(document, slot):
    choices = document['skins'][0]['attachments'].get(slot, {})
    if set(choices) != {slot}: raise ValueError('joint_follow_attachment_variants')
    mesh = choices[slot]
    if mesh.get('type') != 'mesh' or len(mesh.get('vertices', [])) == len(mesh.get('uvs', [])):
        raise ValueError('joint_follow_weighted_mesh_required')
    for animation in document['animations'].values():
        if animation.get('attachments', {}).get('default', {}).get(slot):
            raise ValueError('joint_follow_existing_deform')
        if animation.get('slots', {}).get(slot, {}).get('attachment'):
            raise ValueError('joint_follow_attachment_timeline')
    rows, _ = _rows(mesh)
    drivers = {i for row in rows for i, _, _, w, _ in row if w > 1e-8}
    if len(drivers) != 1 or any(len(row) != 1 or abs(row[0][3]-1) > 1e-8 for row in rows):
        raise ValueError('joint_follow_multiple_drivers')
    return next(iter(drivers)), rows


def pendulum(document, slot, anchor_x=.5, anchor_y=1.):
    """Rotate the whole object about an adjustable parent-local bounding-box pivot.

    No remesh, no UV change and no new implicit reassignment of its parent.
    anchor_y=1 is the local upper edge; the UI exposes both coordinates.
    """
    index, rows = rigid_driver(document, slot)
    points = [(row[0][1], row[0][2]) for row in rows]
    lo = [min(p[d] for p in points) for d in (0, 1)]
    hi = [max(p[d] for p in points) for d in (0, 1)]
    pivot = [lo[d]+(hi[d]-lo[d])*v for d, v in enumerate((anchor_x, anchor_y))]
    driver = document['bones'][index]['name']; helper = 'm5-object-'+slot
    child = len(document['bones'])
    document['bones'].append(dict(name=helper, parent=driver, x=pivot[0], y=pivot[1],
        rotation=0., length=max(8., hi[1]-lo[1])))
    document['skins'][0]['attachments'][slot][slot]['vertices'] = [
        v for x, y in points for v in (1, child, x-pivot[0], y-pivot[1], 1.)]
    center = [(lo[d]+hi[d])/2-pivot[d] for d in (0, 1)]
    wind_axis = math.degrees(math.atan2(center[1], center[0])) if math.hypot(*center) > 1e-8 else -90.
    return dict(slot=slot, helpers=[helper], pinned_vertices=[], region_kind='objects',
        root_driver=driver, pivot_local=pivot, pivot_helper=helper,
        wind_axis_offset=wind_axis,
        strategy='rigid-pendulum-existing-parent', root_policy='adjustable_parent_local_bbox_pivot',
        source_rgba_preserved=True)
