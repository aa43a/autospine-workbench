"""Portable related candidates retain the complete immutable diagnostic bundle."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from .motion_related_evidence import bundle_digest
from .storage_io import canonical_bytes
from ..resolved_project import canonical_sha256


def package(value, files, stage_review=None, supplements=()):
    evidence=value['evidence']
    candidate=bundle_digest(files)
    if candidate!=evidence['candidate_sha256']:
        raise ValueError('motion_related_export_identity')
    extra={
        'related-evidence.json':canonical_bytes(evidence),
        'runtime-report.json':canonical_bytes(value['runtime']),
        'related-receipt.json':canonical_bytes(value['receipt']),
    }
    if stage_review is not None:
        report=stage_review['readiness']
        if (stage_review['artifact_sha256']!=candidate or report['artifact_sha256']!=candidate
                or report['baseline_sha256']!=value['baseline_sha256']
                or report['request_sha256']!=value['request_sha256']
                or report['related_evidence_sha256']!=canonical_sha256(evidence)
                or report['registration_sha256']!=stage_review['registration_sha256']
                or stage_review['evidence_sha256']!=canonical_sha256(report)
                or stage_review['authority']!='none' or stage_review['production_authorized'] is not False):
            raise ValueError('motion_related_export_review_identity')
        extra['related-stage-review.json']=canonical_bytes(stage_review)
    if supplements:
        from .motion_depth_supplement import validate
        if stage_review is None or len(supplements)>16:
            raise ValueError('motion_related_export_supplements')
        for supplement in supplements:
            validate(supplement,stage_review['registration_sha256'],value,files)
            raw=canonical_bytes(supplement)
            name='depth-supplements/'+sha256(raw).hexdigest()+'.json'
            if name in extra:raise ValueError('motion_related_export_duplicate_supplement')
            extra[name]=raw
    manifest=dict(schema='autospine.motion-related-export/v1',candidate_sha256=candidate,
        baseline_sha256=value['baseline_sha256'],request_sha256=value['request_sha256'],
        candidate_files={name:sha256(raw).hexdigest() for name,raw in sorted(files.items())},
        evidence_files={name:sha256(raw).hexdigest() for name,raw in sorted(extra.items())},
        authority='none',selected=False,production_authorized=False,
        limitations=['no_inherited_baseline_acceptance','no_new_runtime_capture',
                    'runtime_pass_does_not_establish_contact_depth_or_visual_acceptance',
                    'supplements_do_not_revise_original_stage_acceptance'])
    if stage_review is not None:
        manifest.update(registration_sha256=stage_review['registration_sha256'],
                        stage_review_revision=stage_review['revision'])
    extra['related-export.json']=canonical_bytes(manifest)
    if set(extra)&set(files):raise ValueError('motion_related_export_reserved_name')
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        for name,raw in sorted(dict(files,**extra).items()):
            entry=ZipInfo(name);entry.compress_type=ZIP_DEFLATED
            archive.writestr(entry,raw)
    return output.getvalue()
