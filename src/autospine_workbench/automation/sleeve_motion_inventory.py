"""Closed motion inventories: legacy v1 never accepts ordinary four-track rows."""
import re

WIDE = 'wide-sleeve-seven-v1'
ORDINARY = 'ordinary-forearm30-hand30-sine129-v1'
PROFILES = {
    WIDE: ('cloth', 'combined_mm', 'combined_mp', 'combined_pm', 'combined_pp', 'forearm', 'hand'),
    ORDINARY: ('combined_opposed', 'combined_same', 'forearm', 'hand'),
}


def motion_names(export, row):
    schema = export.get('schema')
    if schema == 'autospine.sleeve-export-report/v1':
        return PROFILES[WIDE]
    if schema != 'autospine.sleeve-export-report/v2':
        raise ValueError('sleeve_export_schema')
    return explicit_names(row)


def explicit_names(row):
    profile = row.get('motion_profile')
    if profile not in PROFILES or not re.fullmatch('[a-f0-9]{64}', row.get('motion_source_sha256', '')):
        raise ValueError('sleeve_motion_profile')
    return PROFILES[profile]


def metadata(export, row):
    motion_names(export, row)
    return ({key: row[key] for key in ('motion_profile', 'motion_source_sha256')}
            if export['schema'].endswith('/v2') else {})


def evidence_schema(export, kind):
    if export.get('schema') not in ('autospine.sleeve-export-report/v1', 'autospine.sleeve-export-report/v2'):
        raise ValueError('sleeve_export_schema')
    return f'autospine.{kind}/' + export['schema'].rsplit('/', 1)[1]


def checked_names(export, expected, actual):
    names = motion_names(export, expected)
    if any(actual.get(key) != value for key, value in metadata(export, expected).items()):
        raise ValueError('sleeve_motion_source_mismatch')
    return names
