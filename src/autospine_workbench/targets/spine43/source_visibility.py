"""Versioned interpretation of observed visibility, with explicit fields first."""
from copy import deepcopy

PROFILE = 'observed-source-visibility-v1'


def normalize(layer, profile=None):
    if profile is None:
        return layer
    if profile != PROFILE:
        raise ValueError('source_visibility_profile_invalid')
    result = deepcopy(layer)
    observed = layer.get('observed', {})
    if type(observed) is not dict:
        raise ValueError('source_visibility_observation_invalid')
    for key, default in (('empty', False), ('visible', True)):
        value = layer.get(key, observed.get(key, default))
        if type(value) is not bool:
            raise ValueError('source_visibility_flag_invalid')
        result[key] = value
    return result
