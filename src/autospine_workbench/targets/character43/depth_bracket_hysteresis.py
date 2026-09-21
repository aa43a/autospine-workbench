"""Optional stable-order hypothesis inside equally bracketed ambiguous runs."""
from collections import Counter
from .depth_coherent_frame import adjacency

PROFILE='equal-hard-bracket-ambiguous-hold-v1-experiment'


def apply(mesh,models,setup):
    n=len(mesh['triangles'])//3;counts=Counter();records=[];changed=0
    for body,rows in models.items():
        if any(len(r['labels'])!=n or len(r['observed_states'])!=n for r in rows):
            raise ValueError('bracket_hysteresis_inventory')
        if any(b['time']<=a['time'] for a,b in zip(rows,rows[1:])):raise ValueError('bracket_hysteresis_time_order')
        for row in rows:row['pre_bracket_labels']=list(row['labels'])
        for triangle in range(n):
            i=0
            while i<len(rows):
                if rows[i]['observed_states'][triangle]!='A':i+=1;continue
                start=i
                while i<len(rows) and rows[i]['observed_states'][triangle]=='A':i+=1
                left=rows[start-1]['observed_states'][triangle] if start else None
                right=rows[i]['observed_states'][triangle] if i<len(rows) else None
                kind=('same_hard_brackets' if left==right else 'opposite_hard_brackets') if left in ('F','B') and right in ('F','B') else 'incomplete_brackets'
                counts[kind]+=1
                if kind!='same_hard_brackets':continue
                label=int(left=='F');indices=[j for j in range(start,i) if rows[j]['labels'][triangle]!=label]
                if not indices:continue
                for j in indices:rows[j]['labels'][triangle]=label
                changed+=len(indices)
                records.append(dict(body=body,triangle=triangle,start=start,end=i,
                    before_time=rows[start-1]['time'],after_time=rows[i]['time'],bracket_state=left,
                    changed_indices=indices))
        previous=[int(setup[body])]*n
        adjacent=adjacency(mesh)
        for row in rows:
            row['transition_count']=sum(a!=b for a,b in zip(previous,row['labels']));previous=row['labels']
            row['spatial_cuts']=sum(row['labels'][a]!=row['labels'][b] for a,b in adjacent
                if row['observed_states'][a]!='N' and row['observed_states'][b]!='N')
            row['bracket_profile']=PROFILE
    return dict(profile=PROFILE,run_counts=dict(counts),changed_labels=changed,runs=records,
                authority='none',selected=False,scope='stable-order-hypothesis-not-observed-depth')
