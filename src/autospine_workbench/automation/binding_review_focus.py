"""Explain blocked prerequisites without changing policy candidates or decisions."""


def explain(source, proposal):
    faces = [r for r in source.candidate['layers'] if r.get('semantic') == 'body.face']
    if len(faces) != 1:
        return []
    face = faces[0]['layer_id']
    if any(r['layer_id'] == face and r['action'] != 'pending' for r in source.draft['records']):
        return []
    rows = {r['layer_id']: r for r in proposal['rows']}
    dependencies = []
    for binding in source.bindings['bindings']:
        row = rows.get(binding['layer_id'])
        if (row and row['status'] == 'needs_review'
                and row['reason_codes'] == ['policy_capability_unsupported']
                and binding['reason_codes'] == ['head_detail_name_candidate', 'visual_parent_review_required']
                and len(binding['options']) == 1 and binding['options'][0]['id'] == 'rigid:head'):
            dependencies.append(binding['layer_id'])
    if not dependencies:
        return []
    prerequisites = [face]
    face_row = rows.get(face, {})
    neck = face_row.get('evidence', {}).get('neck_layer_id')
    if neck in rows and rows[neck]['status'] == 'needs_review':
        prerequisites.append(neck)
    return [dict(reason_code='head_details_require_face_binding',
                 prerequisite_layer_ids=sorted(set(prerequisites)),
                 dependent_layer_ids=sorted(dependencies),
                 next_action='review_prerequisites_then_rerun_policy',
                 automatic_adoption_guaranteed=False, authority='none')]
