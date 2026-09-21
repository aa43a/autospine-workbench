"""Lossless weighted-vertex/deform compaction for isolated render partitions."""
from copy import deepcopy


def compact(document, partition):
    candidate=deepcopy(document);receipt=deepcopy(partition)
    skin=candidate['skins'][0];attachments=skin['attachments']
    for row in receipt['regions']:
        name=row['slot'];mesh=attachments[name][name];data=mesh['vertices']
        if mesh.get('type')!='mesh' or len(data)==len(mesh['uvs']):
            raise ValueError('partition_compact_weighted_required')
        blocks=[];deform_indices=[];cursor=offset=0
        while cursor<len(data):
            count=data[cursor]
            if type(count) is not int or count<1 or cursor+1+4*count>len(data):
                raise ValueError('partition_compact_weights')
            blocks.append(data[cursor:cursor+1+4*count])
            deform_indices.append(list(range(offset,offset+2*count)))
            cursor+=1+4*count;offset+=2*count
        if len(blocks)*2!=len(mesh['uvs']):raise ValueError('partition_compact_inventory')
        used=sorted(set(mesh['triangles']))
        if any(type(v) is not int or not 0<=v<len(blocks) for v in used):
            raise ValueError('partition_compact_triangles')
        lookup={v:i for i,v in enumerate(used)}
        coordinates=[v for i in used for v in deform_indices[i]]
        mesh['vertices']=[v for i in used for v in blocks[i]]
        mesh['uvs']=[v for i in used for v in mesh['uvs'][2*i:2*i+2]]
        mesh['triangles']=[lookup[v] for v in mesh['triangles']]
        for animation in candidate['animations'].values():
            tracks=animation.get('attachments',{}).get(skin.get('name','default'),{}).get(name,{}).get(name,{})
            if set(tracks)-{'deform'}:raise ValueError('partition_compact_timeline')
            for key in tracks.get('deform',[]):
                if key.get('curve','linear') not in ('linear','stepped'):
                    raise ValueError('partition_compact_curve')
                values=key.get('vertices',[]);start=key.get('offset',0)
                if type(start) is not int or start<0 or start+len(values)>offset:
                    raise ValueError('partition_compact_deform_inventory')
                key['vertices']=[values[i-start] if start<=i<start+len(values) else 0 for i in coordinates]
                key.pop('offset',None)
        row['source_vertex_indices']=used
    receipt.update(compaction_profile='weighted-render-partition-dense-deform-remap-v1',
                   deformation_index_space_preserved=False,deformation_mapping_preserved=True)
    return candidate,receipt
