"""Atomic, headless counterpart of the editor's layer operation protocol."""
from copy import deepcopy
from .motion_layer_edits import PROFILE, LayerEditError, validate, edit_impact

FIELDS = ('dx', 'dy', 'rotation', 'scaleX', 'scaleY')


def empty():
    return dict(profile=PROFILE, transforms=[], draw_order=[])


def apply_operations(snapshot, operations, document):
    original = deepcopy(snapshot)
    index = -1
    try:
        before = validate(empty() if snapshot is None else snapshot, document)
        working = deepcopy(before)
        if not isinstance(operations, list) or len(operations) > 256:
            raise LayerEditError('rig_edit_batch_invalid', '/operations')
        for index, operation in enumerate(operations):
            allowed = {'transform': {'op', 'slot', 'values'}, 'reset': {'op', 'slot'},
                       'order': {'op', 'slots'}, 'replace': {'op', 'value'}}
            if (not isinstance(operation, dict) or not isinstance(operation.get('op'), str)
                    or operation['op'] not in allowed or set(operation) != allowed[operation['op']]):
                raise LayerEditError('rig_edit_operation_invalid', f'/operations/{index}')
            kind = operation['op']
            if kind in ('transform', 'reset'):
                slot = operation['slot']
                if not isinstance(slot, str) or slot not in [row['name'] for row in document['slots']]:
                    raise LayerEditError('motion_layer_target_mismatch', f'/operations/{index}/slot')
                row = next((deepcopy(row) for row in working['transforms'] if row['slot'] == slot),
                           dict(slot=slot, dx=0, dy=0, rotation=0, scaleX=1, scaleY=1))
                working['transforms'] = [row for row in working['transforms'] if row['slot'] != slot]
                if kind == 'transform':
                    values = operation['values']
                    if not isinstance(values, dict) or set(values) - set(FIELDS):
                        raise LayerEditError('rig_edit_property_invalid', f'/operations/{index}/values', slot)
                    row.update(values)
                    # Validate even identity values on unsupported attachments.
                    validate(dict(profile=PROFILE, transforms=[row], draw_order=[]), document)
                    if any(row[key] != (1 if key.startswith('scale') else 0) for key in FIELDS):
                        working['transforms'].append(row)
            elif kind == 'order':
                working['draw_order'] = deepcopy(operation['slots'])
            else:
                working = empty() if operation['value'] is None else deepcopy(operation['value'])
            working = validate(working, document)
        return dict(ok=True, value=working, inverse=[dict(op='replace', value=before)],
                    diagnostics=[], impact=edit_impact(working))
    except LayerEditError as error:
        return dict(ok=False, value=original, diagnostics=[dict(row, operation=index) for row in error.diagnostics])
