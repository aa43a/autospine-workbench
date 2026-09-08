"""Finite, bounded, strictly monotone candidate and full source coverage checks."""
import math


def validate(report):
    if (report.get('schema')!='autospine.continuous-seam-parameters/v1' or report.get('authority')!='none'
            or report.get('production_authorized') is not False or report.get('status')!='needs_review'):
        raise ValueError('parameter_authority')
    for relation in report['analysis']['relations']:
        ids=[p['pair'] for p in relation['blocked_pairs']]
        for group in relation['groups']:
            ids.extend(group['pairs'])
            if group['status']=='blocked':continue
            reference=group['reference_parameters'];samples=group['samples'];sign=group['direction']
            if len(samples)!=len(group['pairs']) or len(reference)!=len(samples) or sign not in (-1,1):raise ValueError('parameter_identity')
            values=[s['parameter'] for s in samples]
            if any(not math.isfinite(v) for v in values+reference+[group['cost'],group['max_world_shift_px']]):raise ValueError('parameter_nonfinite')
            if any(sign*(b-a)<.1-1e-8 for a,b in zip(values,values[1:])):raise ValueError('parameter_order')
            if any(abs(a-b)>2.+1e-8 for a,b in zip(values,reference)) or not 0<=group['max_world_shift_px']<=2.:
                raise ValueError('parameter_displacement')
            if abs(sum((a-b)**2 for a,b in zip(values,reference))-group['cost'])>1e-8:raise ValueError('parameter_cost')
            for s in samples:
                binding=s['embedding']
                if binding is None:raise ValueError('parameter_unmapped')
                weights=binding['barycentric']
                if len(weights)!=3 or any(not math.isfinite(v) or v< -1e-8 for v in weights) or abs(sum(weights)-1)>1e-8:
                    raise ValueError('parameter_embedding')
        if sorted(ids)!=list(range(relation['source_pair_count'])):raise ValueError('parameter_source_coverage')
    return report
