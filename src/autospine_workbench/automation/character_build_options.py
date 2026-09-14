"""Validate saved recipes without rewriting legacy decisions or their identities."""
import re

OPTIONS = ('motion_choice_id', 'residual_texture_profile', 'skirt_profile', 'shoulder_regions')


def valid_regions(value):
    return (type(value) is list and 0 < len(value) <= 16
            and all(type(s) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', s) for s in value)
            and len(set(value)) == len(value))


def valid_options(options):
    return (type(options) is dict and not set(options)-set(OPTIONS)
            and all(valid_regions(v) if k == 'shoulder_regions' else type(v) is str
                    for k, v in options.items()))
