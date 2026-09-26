"""Portable related candidates retain the complete immutable diagnostic bundle."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from .motion_related_evidence import bundle_digest
from .storage_io import canonical_bytes


def package(value, files):
    evidence=value['evidence']
    candidate=bundle_digest(files)
    if candidate!=evidence['candidate_sha256']:
        raise ValueError('motion_related_export_identity')
    extra={
        'related-evidence.json':canonical_bytes(evidence),
        'runtime-report.json':canonical_bytes(value['runtime']),
        'related-receipt.json':canonical_bytes(value['receipt']),
    }
    manifest=dict(schema='autospine.motion-related-export/v1',candidate_sha256=candidate,
        baseline_sha256=value['baseline_sha256'],request_sha256=value['request_sha256'],
        candidate_files={name:sha256(raw).hexdigest() for name,raw in sorted(files.items())},
        evidence_files={name:sha256(raw).hexdigest() for name,raw in sorted(extra.items())},
        authority='none',selected=False,production_authorized=False,
        limitations=['no_inherited_baseline_acceptance','no_new_runtime_capture',
                    'runtime_pass_does_not_establish_contact_depth_or_visual_acceptance'])
    extra['related-export.json']=canonical_bytes(manifest)
    if set(extra)&set(files):raise ValueError('motion_related_export_reserved_name')
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        for name,raw in sorted(dict(files,**extra).items()):
            entry=ZipInfo(name);entry.compress_type=ZIP_DEFLATED
            archive.writestr(entry,raw)
    return output.getvalue()
