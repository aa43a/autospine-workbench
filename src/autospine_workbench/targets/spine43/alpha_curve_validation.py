"""Cross-reference and numeric checks for directed edge anchor reports."""
import math


def validate(report):
    if (report.get('schema')!='autospine.alpha-curve-anchors/v1' or report.get('authority')!='none'
            or report.get('production_authorized') is not False or report.get('status')!='needs_review'):
        raise ValueError('curve_authority_invalid')
    names=set()
    for row in report['curves']['attachments']:
        if row['attachment'] in names:raise ValueError('curve_duplicate_attachment')
        names.add(row['attachment']);edges=set();samples=set()
        for curve in row['curves']:
            points=curve['points'];pixels=curve['edge_pixels']
            if len(points)!=len(pixels)+1 or not pixels:raise ValueError('curve_edge_count')
            if curve['closed']!=(points[0]==points[-1]):raise ValueError('curve_closure')
            for a,b,p in zip(points,points[1:],pixels):
                if any(not isinstance(v,int) for v in a+b+p):raise ValueError('curve_non_integer_edge')
                if sum(abs(a[k]-b[k]) for k in (0,1))!=1:raise ValueError('curve_non_unit_edge')
                edge=(tuple(a),tuple(b))
                if edge in edges:raise ValueError('curve_duplicate_edge')
                edges.add(edge)
        if len(edges)!=row['boundary_edges']:raise ValueError('curve_boundary_count')
        for anchor in row['anchors']:
            sample=anchor['source_sample'];options=anchor['options']
            if sample in samples:raise ValueError('curve_duplicate_sample')
            samples.add(sample)
            expected='missing_edge' if not options else ('ambiguous_projection' if len(options)>1 else
                      ('unmapped_mesh' if options[0]['embedding'] is None else 'candidate_anchor'))
            if anchor['status']!=expected:raise ValueError('curve_anchor_status')
            for option in options:
                ci,ei=option['curve'],option['edge']
                if not 0<=ci<len(row['curves']):raise ValueError('curve_reference')
                curve=row['curves'][ci]
                if not 0<=ei<len(curve['edge_pixels']):raise ValueError('curve_edge_reference')
                a,b=curve['points'][ei:ei+2]
                if option['t']!=.5 or option['pixel_xy']!=[(x+y)/2 for x,y in zip(a,b)]:raise ValueError('curve_projection')
                if option['u']!=(ei+.5)/len(curve['edge_pixels']):raise ValueError('curve_parameter')
                binding=option['embedding']
                if binding is not None:
                    weights=binding['barycentric'];triangle=binding['triangle']
                    if (len(weights)!=3 or len(triangle)!=3 or any(not math.isfinite(v) or v< -1e-8 for v in weights)
                            or abs(sum(weights)-1)>1e-8):raise ValueError('curve_embedding')
    return report
