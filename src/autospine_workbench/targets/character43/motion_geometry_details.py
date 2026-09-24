"""Source-texture locations for exact sampled failures; never changes QA gates."""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np
from .numeric_reference import read
from .affine_pose import matrices, sample
from .projected_area_reference import reference as projected_reference
from .triangle_shape_evidence import build as shape_evidence


def build(files, artifact, *, limit=12):
    if type(limit) is not int or not 1 <= limit <= 24:
        raise ValueError('geometry_detail_limit')
    required={'skeleton.json','deformation.json','numeric-reference.json','rig-setup-reference.json'}
    missing=sorted(required-files.keys())
    if missing:
        return dict(profile='motion-geometry-source-locations-v1',artifact_sha256=artifact,
                    status='unavailable',missing=missing,rows=[],authority='none',selected=False)
    doc=json.loads(files['skeleton.json']);digest=sha256(files['skeleton.json']).hexdigest()
    qa=json.loads(files['deformation.json']);samples=read(files)
    setup=json.loads(files['rig-setup-reference.json'])
    if any(r.get('skeleton_sha256')!=digest for r in (qa,samples,setup)):
        raise ValueError('geometry_detail_identity_mismatch')
    if qa.get('profile')=='character-active-attachment-deformation-v1':
        return dict(profile='motion-geometry-source-locations-v1',artifact_sha256=artifact,
            skeleton_sha256=digest,status='unavailable',rows=[],authority='none',selected=False,
            reason='active_attachment_source_locations_not_supported',
            note='姿态附件几何失败已保留；固定网格定位器不能将新附件索引映射到原纹理。')
    rows=[];budget=20_000_000
    for record in qa['records']:
        if record['passed']:continue
        name,slot=record['animation'],record['slot']
        mesh=doc['skins'][0]['attachments'][slot][slot]
        triangles=np.asarray(mesh['triangles'],dtype=int).reshape(-1,3)
        frames=samples['animations'][name]
        budget-=len(frames)*len(triangles)
        if budget<0:raise ValueError('geometry_detail_sample_budget')
        base=np.asarray(setup['vertices'][slot],dtype=float)
        def areas(points):
            p=points[triangles];a=p[:,1]-p[:,0];b=p[:,2]-p[:,0]
            return (a[:,0]*b[:,1]-a[:,1]*b[:,0])/2
        original=areas(base)
        if np.any(np.abs(original)<1e-10):raise ValueError('geometry_detail_setup_degenerate')
        worst=np.full(len(triangles),np.inf);indices=np.zeros(len(triangles),dtype=int)
        maximum=np.full(len(triangles),-np.inf);counts=np.zeros(len(triangles),dtype=int)
        max_indices=np.zeros(len(triangles),dtype=int)
        if not frames:raise ValueError('geometry_detail_empty_samples')
        for index,frame in enumerate(frames):
            points=np.asarray(frame['vertices'][slot],dtype=float)
            if points.shape!=base.shape or not np.isfinite(points).all():
                raise ValueError('geometry_detail_nonfinite')
            ratios=areas(points)/original;changed=ratios<worst
            worst[changed]=ratios[changed];indices[changed]=index
            max_changed=ratios>maximum;max_indices[max_changed]=index
            maximum=np.maximum(maximum,ratios);counts+=(ratios<.5)|(ratios>2)
        # This screen explains area failures; edge-only failures remain explicitly separate.
        failed=np.flatnonzero(counts)
        events=[(int(i),'area_compression',int(indices[i]),float(worst[i]),.5-worst[i])
                for i in failed if worst[i]<.5]
        events += [(int(i),'area_expansion',int(max_indices[i]),float(maximum[i]),maximum[i]-2)
                   for i in failed if maximum[i]>2]
        selected=sorted(events,key=lambda row:-row[4])[:limit]
        data=mesh['vertices'];influences=[];cursor=0
        if len(data)==len(mesh['uvs']):
            bone_name=next(s['bone'] for s in doc['slots'] if s['name']==slot)
            bone_index=next(i for i,b in enumerate(doc['bones']) if b['name']==bone_name)
            influences=[[(bone_index,1.0)] for _ in base]
        else:
            while cursor<len(data):
                n=data[cursor];cursor+=1
                influences.append([(data[cursor+4*j],data[cursor+4*j+3]) for j in range(n)])
                cursor+=4*n
        rest=deepcopy(doc);rest['animations']={name:{'bones':{}}};rest_matrix=matrices(rest,name,0)
        uncorrected=deepcopy(doc)
        uncorrected['animations'][name].pop('attachments',None)
        uncorrected['animations'][name].pop('deform',None)
        raw_frames={}
        details=[]
        for i,reason,frame_index,ratio,_severity in selected:
            frame=frames[frame_index];time=frame['time']
            try:
                refs=projected_reference(original.tolist(),triangles.tolist(),influences,doc['bones'],
                                         rest_matrix,matrices(doc,name,time))
                refs_ratio=float(refs[i]/original[i])
            except ValueError:
                refs_ratio=None  # A proxy limitation must not hide the measured failure.
            tri=triangles[i].tolist()
            if time not in raw_frames:
                raw_frames[time]=sample(uncorrected,name,time)[0][slot]
            p=np.asarray(raw_frames[time],dtype=float)[tri]
            a,b=p[1]-p[0],p[2]-p[0]
            uncorrected_ratio=float((a[0]*b[1]-a[1]*b[0])/2/original[i])
            details.append(dict(triangle=int(i),vertices=tri,time=time,reason=reason,setup_ratio=ratio,
                without_deform_setup_ratio=uncorrected_ratio,
                deform_area_delta_ratio=ratio-uncorrected_ratio,
                minimum_setup_ratio=float(worst[i]),
                maximum_setup_ratio=float(maximum[i]),failed_samples=int(counts[i]),
                projected_reference_ratio=refs_ratio,
                ratio_to_projected_reference=float(ratio/refs_ratio) if refs_ratio is not None and abs(refs_ratio)>1e-10 else None,
                texture_uv=[mesh['uvs'][v*2:v*2+2] for v in tri],
                sampled_world=[frame['vertices'][slot][v] for v in tri],
                bones=sorted({doc['bones'][b]['name'] for v in tri for b,w in influences[v] if w>0})))
            try:
                details[-1]['shape_evidence']=shape_evidence(base[tri],
                    np.asarray(frame['vertices'][slot])[tri],p,[influences[v] for v in tri],
                    doc['bones'],rest_matrix,matrices(doc,name,time))
            except ValueError as exc:
                details[-1]['shape_evidence']=dict(status='unavailable',reason=str(exc))
        texture=files['images/'+mesh.get('path',slot)+'.png']
        if len(texture)>8*1024*1024:raise ValueError('geometry_detail_texture_budget')
        rows.append(dict(slot=slot,animation=name,failed_area_triangles=len(failed),
            shown=len(details),truncated=len(events)>len(details),sample_count=len(frames),
            texture='data:image/png;base64,'+b64encode(texture).decode(),details=details,
            next_action='compare_pose_attachment_or_partition' if details else 'inspect_edge_stretch',
            note='移除 deform 的对照保留相同骨骼、权重与时间，仅用于分析修正影响，不是修复方案。投影参考是近似模型；所有比值均不改变原几何门禁。'))
    return dict(profile='motion-geometry-source-locations-v1',artifact_sha256=artifact,
                skeleton_sha256=digest,rows=rows,status='available',authority='none',selected=False,
                scope='sampled_area_locations_not_automatic_artwork_requirement_or_acceptance')
