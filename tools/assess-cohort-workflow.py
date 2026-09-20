"""Read current whole-character acceptance after a verified first-ten intake snapshot."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from autospine_workbench.automation.cohort_intake import assess
from autospine_workbench.automation.cohort_workflow import selected_project, summarize
from autospine_workbench.automation.cohort_workflow_report import render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intake', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8918')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    origin = urlsplit(args.base_url)
    if (origin.scheme != 'http' or origin.hostname not in ('localhost', '127.0.0.1')
            or origin.path or origin.query or origin.fragment or origin.username or origin.password):
        parser.error('base URL must be a local workbench origin')
    def raw(path):
        with urlopen(args.base_url + path, timeout=300) as response:
            return response.read(32 << 20)
    def get(path):
        return json.loads(raw(path))
    def saved(name):
        return json.loads((args.intake / name).read_bytes())
    intake = saved('report.json'); catalog = saved('catalog.json')
    for name, field in [('manifest.json', 'manifest_sha256'), ('catalog.json', 'catalog_sha256'),
                        ('source-checks.json', 'source_checks_sha256')]:
        if sha256((args.intake / name).read_bytes()).hexdigest() != intake[field]:
            raise ValueError('intake_snapshot_digest_mismatch')
    selected = saved('manifest.json')
    if 'source_versions_sha256' in intake:
        from autospine_workbench.automation.cohort_versions import select
        version_raw = (args.intake / 'source-versions.json').read_bytes()
        if sha256(version_raw).hexdigest() != intake['source_versions_sha256']:
            raise ValueError('intake_versions_changed')
        selected = select(selected, (args.intake / 'manifest.json').read_bytes(), json.loads(version_raw))
    replay = assess(selected, catalog, saved('source-checks.json'))
    if replay['characters'] != intake['characters']:
        raise ValueError('intake_report_changed')
    def catalog_identity(value):
        return {p['id']: [p['lifecycle'], p.get('source')] for p in value['projects']}
    if catalog_identity(get('/api/asset-library')) != catalog_identity(catalog):
        raise ValueError('catalog_changed_rerun_verified_intake')
    documents = saved('project-documents.json'); observations = {}
    for row in intake['characters']:
        project = selected_project(row)
        if project is None:
            continue
        prefix = '/api/projects/' + quote(project, safe='')
        document = get(prefix)
        if document['id'] != project or document['source'] != documents[project]['source']:
            raise ValueError('project_source_changed_rerun_intake')
        current = get(prefix + '/automation/character'); job = current.get('job')
        if current['project_id'] != project or current['authority'] != 'none':
            raise ValueError('workflow_project_mismatch')
        item = dict(job=job, reason_code=current.get('reason_code'))
        from autospine_workbench.resolved_project import canonical_sha256
        work = get(prefix + '/automation/character/work-sessions')
        if work['project_id'] != project or work['authority'] != 'none' or work['source_sha256'] != canonical_sha256(document['source']):
            raise ValueError('work_session_source_mismatch')
        item['verified_work_sessions'] = work
        if job and job['status'] == 'needs_review':
            endpoint = prefix + '/automation/character/jobs/' + job['job_id']
            encoded = raw(endpoint + '/view/report.json'); report = json.loads(encoded)
            if (sha256(encoded).hexdigest() != job['runtime']['files']['report.json']
                    or report.get('bundle_sha256') != job['artifact_sha256']
                    or report.get('schema') != 'autospine.character-framebuffer/v1'
                    or report.get('runtime_package') != '@esotericsoftware/spine-webgl'
                    or report.get('runtime_version') != '4.3.13' or report.get('authority') != 'none'):
                raise ValueError('runtime_source_mismatch')
            visual = get(endpoint + '/visual-review'); weighted = get(endpoint + '/weighted-review')
            for value in (visual, weighted):
                if any(value.get(k) != job[k] for k in ('project_id', 'job_id', 'artifact_sha256')):
                    raise ValueError('review_source_mismatch')
            item.update(verified_runtime=report, visual_review=visual['review'], weighted_review=weighted)
            item['auto_binding_audit'] = get(endpoint + '/auto-binding-audit')
        observations[project] = item
        print(project + ': observed', flush=True)
    result = summarize(intake, observations)
    result['intake_report_sha256'] = sha256((args.intake / 'report.json').read_bytes()).hexdigest()
    result['observations_sha256'] = sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'observations.json').write_text(json.dumps(observations, sort_keys=True), encoding='utf-8')
    (args.output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output / 'index.html').write_text(render(result, args.base_url), encoding='utf-8')
    print(json.dumps(result['metrics']))


if __name__ == '__main__':
    main()
