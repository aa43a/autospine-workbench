"""Exact bind/texture compatibility, independent of visual acceptance or QA."""
from copy import deepcopy
from hashlib import sha256
import json

from ...resolved_project import canonical_sha256

PROFILE = 'exact-bind-texture-animation-compatibility-v1'


def signature(files):
    document = json.loads(files['skeleton.json'])
    if (not isinstance(document.get('animations'), dict) or not document['animations']
            or not document.get('bones') or not document.get('slots') or not document.get('skins')):
        raise ValueError('animation_compatibility_source_invalid')
    rig = deepcopy(document)
    rig.pop('animations')
    # Spine's descriptive export hash is not a binding parameter. Everything
    # else, including setup transforms, draw order, attachment paths and UVs,
    # must match. Similar bone names alone do not establish compatibility.
    rig.get('skeleton', {}).pop('hash', None)
    assets = {name: sha256(raw).hexdigest() for name, raw in files.items()
              if name.endswith('.atlas') or name.startswith(('images/', 'textures/', 'editor/images/'))}
    if 'skeleton.atlas' not in assets or not any(n.startswith('textures/') for n in assets):
        raise ValueError('animation_compatibility_textures_missing')
    sections = {name: canonical_sha256(value) for name, value in rig.items()}
    sections['texture_assets'] = canonical_sha256(assets)
    return dict(profile=PROFILE, signature_sha256=canonical_sha256(sections), sections=sections,
                animations=sorted(document['animations']),
                authority='none', runtime_recheck_required=True)


def compare(first, second):
    return sorted(key for key in set(first['sections']) | set(second['sections'])
                  if first['sections'].get(key) != second['sections'].get(key))
