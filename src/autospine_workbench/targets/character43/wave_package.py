"""Admit a frozen wave only when the current whole-scene geometry passes."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from ...motion_builtin import build_builtin_motion
from ..spine43.continuous_pose import world
from .wave_motion import build_wave
from .deformation_qa import inspect


def append_wave(files,checkpoint=lambda:None):
    result=dict(files);manifest=json.loads(files['character-manifest.json'])
    if manifest['profile']!='ordinary-motionir-idle-v1':raise ValueError('character_wave_source_unsupported')
    document=json.loads(files['skeleton.json'])
    try:
        wave,evidence=build_wave(document);frames=[]
        for tick in range(129):
            if tick%16==0:checkpoint()
            frames.append(dict(time=tick/64,vertices=world(wave,tick/64)))
        raw=canonical_bytes(wave);reference=canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(),animations={'wave-left':frames}))
        qa=inspect({'skeleton.json':raw,'numeric-reference.json':reference})
        result['wave-deformation.json']=canonical_bytes(qa)
        result['wave-retarget.json']=canonical_bytes(evidence)
        readiness=dict(clip='wave-left',status='candidate' if qa['passed'] else 'blocked',
                       reason_code=None if qa['passed'] else 'character_wave_geometry_failed',
                       failing_slots=[r['slot'] for r in qa['records'] if not r['passed']])
        if qa['passed']:
            document['animations'].update(wave['animations']);result['skeleton.json']=canonical_bytes(document)
            if 'editor/skeleton.json' in result:result['editor/skeleton.json']=result['skeleton.json']
            existing=json.loads(files['numeric-reference.json']);existing['animations']['wave-left']=frames
            existing['skeleton_sha256']=sha256(result['skeleton.json']).hexdigest();result['numeric-reference.json']=canonical_bytes(existing)
    except ValueError as exc:
        if not str(exc).startswith('character_wave_'):raise
        readiness=dict(clip='wave-left',status='blocked',reason_code=str(exc),failing_slots=[])
    result['wave-motion-ir.json']=build_builtin_motion('wave.left').canonical_json.encode()
    manifest.update(profile='ordinary-motionir-wave-gated-v1',animations=list(document['animations']),motion_readiness=[readiness])
    manifest['files']={n:sha256(raw).hexdigest() for n,raw in sorted(result.items()) if n!='character-manifest.json'}
    result['character-manifest.json']=canonical_bytes(manifest)
    return result
