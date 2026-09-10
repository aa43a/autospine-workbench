"""Source-bound software contact summaries; never promote them to GPU evidence."""
from .storage_io import read_document
from ..resolved_project import canonical_sha256
from .sleeve_motion_inventory import checked_names,evidence_schema


def summaries(root,project,export):
    paths=list((root/'contacts'/project).glob('*.json'))
    if len(paths)!=1:raise ValueError('sleeve_contact_report_inventory')
    doc=read_document(paths[0])
    if (paths[0].stem!=canonical_sha256(doc) or doc.get('schema')!=evidence_schema(export,'sleeve-contact-coverage')
            or doc.get('project_id')!=project or doc.get('source_sha256')!=canonical_sha256(export)
            or doc.get('authority')!='none' or doc.get('production_authorized') is not False
            or doc.get('framebuffer_status')!='not_evaluated'):raise ValueError('sleeve_contact_report_source')
    expected={(r['layer_id'],r['component_id']):r for r in export['records'] if r['status']=='candidate_exported'}
    rows={}
    for row in doc['records']:
        key=row['layer_id'],row['component_id']
        if key in rows or key not in expected or row['asset_sha256']!=expected[key]['files']:
            raise ValueError('sleeve_contact_region_inventory')
        if row['authority']!='none' or row['production_authorized'] is not False or row['framebuffer_status']!='not_evaluated':
            raise ValueError('sleeve_contact_authority')
        count,failed,missing=(row[k] for k in ('tested_samples','failed_samples','unobservable_interfaces'))
        names=checked_names(export,expected[key],row)
        if (len(row['tracks'])!=len(names) or {t['animation'] for t in row['tracks']}!=set(names)
                or any(t['frames']!=257 for t in row['tracks'])):raise ValueError('sleeve_contact_motion_inventory')
        if any(type(v) is not int or v<0 for v in (count,failed,missing)) or failed>count:raise ValueError('sleeve_contact_counts')
        eligible=sum(len(r['samples']) for r in row['interfaces'])
        if (count!=eligible*sum(t['frames'] for t in row['tracks']) or failed!=sum(t['failed_samples'] for t in row['tracks'])
                or missing!=sum(not r['samples'] for r in row['interfaces'])):raise ValueError('sleeve_contact_counts')
        status='cpu_coverage_passed' if count and not failed and not missing else 'needs_review'
        if row['status']!=status:raise ValueError('sleeve_contact_status')
        rows[key]=dict(status=status,tested_samples=count,failed_samples=failed,unobservable_interfaces=missing,
            report_sha256=canonical_sha256(doc),framebuffer_status='not_evaluated')
    if rows.keys()!=expected.keys():raise ValueError('sleeve_contact_region_inventory')
    return rows
