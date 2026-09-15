"""Derived, reversible ordinary-route default from reviewed narrow arm evidence."""
from ..resolved_project import canonical_sha256


def derive(project, geometry):
    from .project_route import suggest
    rows=(geometry or {}).get('records',[])
    if suggest(project,geometry)[0]=='sleeves' or not rows:return None
    allowed={'narrow_shape_not_sleeveless_proof'}
    narrow=({r.get('side') for r in rows}=={'left','right'} and not any(
            r.get('classification')!='no_broad_shape_evidence'
            or set(r.get('reason_codes',[]))!=allowed for r in rows))
    combined=all(r.get('side')=='bilateral' and r.get('classification')=='insufficient_evidence'
                 and r.get('reason_codes')==['character_side_unknown'] for r in rows)
    if not (narrow or combined):
        return None
    return dict(schema='autospine.project-route-default/v1',profile='reviewed-narrow-arms-v1' if narrow else 'combined-arm-preview-first-v1',
                project_id=geometry['project_id'],source_sha256=project['resolved']['sha256'],
                evidence_sha256=canonical_sha256(geometry),choice='ordinary',decision_source='policy_auto',
                authority='none',production_authorized=False,reversible=True,
                binding_approved=False,sleeveless_inferred=False)
