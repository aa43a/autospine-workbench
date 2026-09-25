"""Exact-time and immutable-input coverage for bounded official captures."""
from hashlib import sha256
import math
from autospine_workbench.automation.storage_io import canonical_bytes


def partition(times,size=4096):
    if (type(size) is not int or not 2<=size<=4097 or not times or len(times)>16385
            or any(not math.isfinite(t) or t<0 for t in times) or times!=sorted(set(times))):
        raise ValueError('runtime_batch_times_invalid')
    # Existing geometry/reference readers require the time-zero anchor per run.
    if times[0]!=0:raise ValueError('runtime_batch_setup_time_required')
    chunks=[times[:size]]
    chunks.extend([[times[0]]+times[i:i+size-1] for i in range(size,len(times),size-1)])
    return chunks


def render_identity(files):
    names=['skeleton.json','skeleton.atlas']
    names.extend(sorted(k for k in files if k.endswith('.png')))
    return sha256(canonical_bytes({k:sha256(files[k]).hexdigest() for k in names})).hexdigest()


def verify(times,batches):
    covered=[];identities=set();runtimes=set()
    for index,batch in enumerate(batches):
        report=batch['runtime'];actual=[r['time'] for r in report['results']]
        if (report['bundle_sha256']!=batch['bundle_sha256'] or report.get('passed') is not True
                or report.get('authority')!='none' or report.get('production_authorized') is not False
                or actual!=batch['times'] or any(r['animation']!='external-motion' for r in report['results'])
                or not batch['geometry_passed']):
            raise ValueError('runtime_batch_capture_mismatch')
        if index and (not actual or actual[0]!=times[0]):raise ValueError('runtime_batch_anchor_missing')
        covered.extend(actual[1:] if index else actual);identities.add(batch['render_identity'])
        runtimes.add((report['runtime_sha256'],report['runtime_version'],report['profile'],report['browser_sha256'],
                      report.get('harness_sha256'),report.get('tool_sha256'),report.get('reference_reader_sha256')))
    if covered!=times or len(identities)!=1 or len(runtimes)!=1:
        raise ValueError('runtime_batch_coverage_or_identity_mismatch')
    return dict(passed=True,frames=len(covered),batches=len(batches),render_identity=next(iter(identities)),
        runtime_version=next(iter(runtimes))[1],runtime_sha256=next(iter(runtimes))[0],
        times_sha256=sha256(canonical_bytes(times)).hexdigest(),authority='none',selected=False,
        scope='declared_times_official_runtime_not_contact_or_visual_acceptance')
