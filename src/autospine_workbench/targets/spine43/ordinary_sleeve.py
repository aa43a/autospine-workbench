"""Three-bone ordinary-sleeve export without fabricated cloth bones or tracks."""
from copy import deepcopy
import math
from ...asset.planning.sleeve_helpers import frames
from ...asset.planning.ordinary_sleeve import angles, MOTIONS, PROFILE
from ...asset.planning.ordinary_sleeve_validation import validate
from ...asset.planning.component_local_solver import metrics
from ...asset.planning.component_temporal_qa import passed
from ...asset.joints.mesh_weights import _deform
from ...resolved_project import canonical_sha256
from .continuous_pose import world


def compile_region(source, row, mesh, skeleton):
    validate(source, skeleton)
    if (source.get('schema') != 'autospine.ordinary-sleeve-motion/v1'
            or source.get('skeleton_sha256') != canonical_sha256(skeleton)
            or source.get('authority') != 'none' or source.get('production_authorized') is not False
            or source.get('profile') != PROFILE or row not in source['records'] or row.get('helper')
            or mesh['vertices_xy'] != row['setup_vertices'] or mesh['triangles'] != row['triangles']):
        raise ValueError('ordinary_sleeve_target_source_mismatch')
    tracks = row.get('tracks', [])
    if row.get('status') != 'candidate_requires_review' or not tracks or any(track['failed_ticks'] for track in tracks):
        raise ValueError('ordinary_sleeve_target_geometry_blocked')
    if [(track['bone_id'], tuple(track['amplitudes'])) for track in tracks] != list(MOTIONS):
        raise ValueError('ordinary_sleeve_target_motion_inventory')
    lookup = {bone['id']: bone for bone in skeleton['bones']}
    chain = [lookup[bone] for bone in row['bone_ids']]
    if len(chain) != 3 or any(track['drivers'] != row['bone_ids'][1:] for track in tracks):
        raise ValueError('ordinary_sleeve_target_driver_mismatch')
    bones = []
    for bone in skeleton['bones']:
        local = bone['setup_local']
        item = dict(name=bone['id'], x=local['x'], y=-local['y'], rotation=-local['rotation_degrees'], length=bone['length'])
        if bone['parent_id'] is not None:
            item['parent'] = bone['parent_id']
        bones.append(item)
    indices = {bone['name']: i for i, bone in enumerate(bones)}
    vertices = []
    for entries in row['weights']:
        if abs(sum(entry['weight'] for entry in entries) - 1) > 1e-9:
            raise ValueError('ordinary_sleeve_target_weight_sum')
        vertices.append(len(entries))
        for entry in entries:
            vertices.extend([indices[entry['bone_id']], entry['local_xy'][0], -entry['local_xy'][1], entry['weight']])
    name = row['layer_id'] + '-' + row['component_id']
    animations = {}
    for track in tracks:
        rotation = {driver: {'rotate': []} for driver in track['drivers']}
        for tick in range(129):
            for driver, angle in zip(track['drivers'], angles(track['amplitudes'], tick)):
                rotation[driver]['rotate'].append(dict(time=tick/64, value=-angle))
        animations[track['bone_id']] = dict(bones=rotation)
    width, height = skeleton['canvas']
    doc = dict(skeleton=dict(spine='4.3.26', hash=canonical_sha256(source), images='./images/',
                            x=0, y=-height, width=width, height=height, fps=64),
               bones=bones, slots=[dict(name=name, bone=chain[1]['id'], attachment=name)], constraints=[],
               skins=[dict(name='default', attachments={name: {name: dict(type='mesh', path=name,
                   uvs=[v for point in mesh['uvs'] for v in point], vertices=vertices,
                   triangles=[v for tri in row['triangles'] for v in tri])}})], animations=animations)
    checks = {}
    for track in tracks:
        probe = deepcopy(doc); probe['animations'] = {track['bone_id']: animations[track['bone_id']]}
        qa, errors = [], []
        for sample in range(257):
            tick = sample/2
            actual = [[x, -y] for x, y in world(probe, tick/64)[name]]
            expected = _deform(row['weights'], frames(chain, dict(zip(track['drivers'], angles(track['amplitudes'], tick)))))
            errors.append(max(math.dist(a, b) for a, b in zip(actual, expected)))
            qa.append(metrics(row['setup_vertices'], actual, row['triangles']))
        checks[track['bone_id']] = dict(key_error_px=max(errors[::2]), midpoint_error_px=max(errors[1::2]),
                                       failed_samples=sum(not passed(value) for value in qa), sample_count=257)
    return doc, dict(target='4.3.26', checks=checks,
                     passed=all(c['key_error_px'] <= 1e-7 and c['failed_samples'] == 0 for c in checks.values()),
                     authority='none', production_authorized=False,
                     runtime_status='not_evaluated', alpha_contact_status='not_evaluated')
