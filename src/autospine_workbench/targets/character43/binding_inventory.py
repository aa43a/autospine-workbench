"""Describe actual vertex influences; this is evidence, not semantic approval."""
import math


def inspect(document,layers):
    if len(document.get('skins',[]))!=1:raise ValueError('binding_inventory_skin_unsupported')
    bones=[b['name'] for b in document['bones']]
    if len(set(bones))!=len(bones):raise ValueError('binding_inventory_duplicate_bone')
    attachments=document['skins'][0]['attachments'];rows=[]
    for layer in layers:
        for region in layer.get('regions',[]):
            if region.get('state')!='weighted_candidate':continue
            key=region['region_id'];attachment=attachments[key][key]
            if attachment.get('type')!='mesh':raise ValueError('binding_inventory_attachment_unsupported')
            data=attachment['vertices'];uvs=attachment['uvs']
            if not uvs or len(uvs)%2 or len(data)>2000000:raise ValueError('binding_inventory_size_invalid')
            i=0;vertices=0;largest=0;max_error=0.;totals={}
            while i<len(data):
                count=data[i];i+=1
                if type(count) is not int or not 1<=count<=64 or i+count*4>len(data):raise ValueError('binding_inventory_encoding_invalid')
                total=0.;seen=set();positive=0
                for _ in range(count):
                    index,x,y,weight=data[i:i+4];i+=4
                    if type(index) is not int or not 0<=index<len(bones) or index in seen:raise ValueError('binding_inventory_bone_invalid')
                    seen.add(index)
                    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x,y,weight)) or not 0<=weight<=1:
                        raise ValueError('binding_inventory_weight_invalid')
                    total+=weight
                    if weight>0:
                        positive+=1
                        row=totals.setdefault(index,dict(bone=bones[index],vertex_count=0,min_weight=1.,max_weight=0.,weight_total=0.))
                        row['vertex_count']+=1;row['min_weight']=min(row['min_weight'],weight)
                        row['max_weight']=max(row['max_weight'],weight);row['weight_total']+=weight
                error=abs(total-1)
                if error>1e-6:raise ValueError('binding_inventory_weight_sum')
                max_error=max(max_error,error);largest=max(largest,positive);vertices+=1
            if vertices!=len(uvs)//2:raise ValueError('binding_inventory_vertex_count')
            influences=[]
            for index,row in sorted(totals.items()):
                influences.append({k:v for k,v in row.items() if k!='weight_total'}|dict(mean_weight=row['weight_total']/vertices))
            rows.append(dict(layer_id=layer['layer_id'],region_id=key,vertex_count=vertices,
                             max_influences=largest,max_weight_sum_error=max_error,influences=influences))
    return dict(schema='autospine.weighted-binding-inventory/v1',authority='none',semantic_review='not_inferred',regions=rows)
