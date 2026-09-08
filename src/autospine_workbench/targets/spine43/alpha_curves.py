"""Directed alpha pixel-cell edges and mesh-embedded seam anchors (no adoption)."""
from collections import defaultdict
from io import BytesIO
from .alpha_seam import embed


def trace(mask):
    """Keep filled cells on the right in image coordinates; split ambiguous corners."""
    height=len(mask);width=len(mask[0]) if height else 0
    if any(len(row)!=width for row in mask):raise ValueError('curve_mask_shape')
    edges=[]
    def filled(x,y):return 0<=x<width and 0<=y<height and bool(mask[y][x])
    for y in range(height):
        for x in range(width):
            if not filled(x,y):continue
            for dx,dy,a,b in ((0,-1,(x,y),(x+1,y)),(1,0,(x+1,y),(x+1,y+1)),
                              (0,1,(x+1,y+1),(x,y+1)),(-1,0,(x,y+1),(x,y))):
                if not filled(x+dx,y+dy):edges.append((a,b,(x,y)))
    outgoing=defaultdict(list);incoming=defaultdict(list)
    for i,(a,b,_) in enumerate(edges):outgoing[a].append(i);incoming[b].append(i)
    ambiguous={p for p in set(outgoing)|set(incoming) if len(outgoing[p])!=1 or len(incoming[p])!=1}
    pending=set(range(len(edges)));curves=[]
    starts=[i for i,e in enumerate(edges) if e[0] in ambiguous]
    for start in starts+list(range(len(edges))):
        if start not in pending:continue
        order=[];current=start
        while current in pending:
            pending.remove(current);order.append(current);end=edges[current][1]
            if end in ambiguous:break
            current=outgoing[end][0]
        points=[list(edges[i][0]) for i in order]+[list(edges[order[-1]][1])]
        curves.append({'points':points,'edge_pixels':[list(edges[i][2]) for i in order],
                       'closed':points[0]==points[-1],
                       'status':'ambiguous_corner' if tuple(points[0]) in ambiguous or tuple(points[-1]) in ambiguous else 'closed_contour'})
    return curves


def anchors(curves,samples,selected,attachment,size):
    """Project original centers onto their own exposed cell edges, preserving ties."""
    index=defaultdict(list);width,height=size
    for ci,curve in enumerate(curves):
        for ei,pixel in enumerate(curve['edge_pixels']):index[tuple(pixel)].append((ci,ei))
    uvs=list(zip(attachment['uvs'][::2],attachment['uvs'][1::2]));flat=attachment['triangles']
    triangles=[flat[i:i+3] for i in range(0,len(flat),3)];result=[]
    for si in sorted(set(selected)):
        pixel=samples[si]['pixel_xy'];options=[]
        for ci,ei in index[tuple(pixel)]:
            curve=curves[ci];a,b=curve['points'][ei:ei+2]
            point=[(a[k]+b[k])/2 for k in (0,1)]
            binding=embed((point[0]/width,point[1]/height),uvs,triangles)
            options.append({'curve':ci,'edge':ei,'t':.5,'u':(ei+.5)/len(curve['edge_pixels']),
                            'pixel_xy':point,'embedding':binding})
        status='missing_edge' if not options else ('ambiguous_projection' if len(options)>1 else
               ('unmapped_mesh' if options[0]['embedding'] is None else 'candidate_anchor'))
        result.append({'source_sample':si,'status':status,'options':options})
    return result


def analyze(doc,files,boundary_report):
    from PIL import Image
    attachments={name:slot[name] for name,slot in doc['skins'][0]['attachments'].items()}
    records=[]
    for name in sorted({r[s] for r in boundary_report['relations'] for s in ('driver','follower')}):
        with Image.open(BytesIO(files['editor/images/'+name+'.png'])) as image:
            alpha=image.convert('RGBA').getchannel('A');width,height=alpha.size
            values=alpha.tobytes();mask=[[values[y*width+x]>=8 for x in range(width)] for y in range(height)]
        curves=trace(mask);samples=boundary_report['boundaries'][name]['samples']
        selected=[p[side+'_sample'] for r in boundary_report['relations'] for side in ('driver','follower')
                  if r[side]==name for p in r['pairs']]
        mapped=anchors(curves,samples,selected,attachments[name],[width,height])
        records.append({'attachment':name,'size':[width,height],'curves':curves,'anchors':mapped,
                        'boundary_edges':sum(len(c['edge_pixels']) for c in curves),
                        'status':'needs_review'})
    return {'profile':'alpha8-directed-cell-edge-v1','attachments':records,'authority':'none',
            'geometry':'thresholded_pixel_cell_boundary','shape_solver':'not_run'}
