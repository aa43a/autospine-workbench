"""Workbench access to current policy evidence and reversible selections."""
from ..http_json_request import read_json_object_request, HttpJsonRequestError
from ..benchmark.artifacts import _folder
from ..manifest_artifacts import require_sha256
from .animated_inputs import load_inputs, _registrations, AnimatedSourceError
from .head_binding_policy import propose
from .simple_binding_adoption import apply, undo, read_decision, KIND


def overview(store, project):
    with load_inputs(store,project) as source:
        result=propose(source)
        names={r['layer_id']:r['name'] for r in source.candidate['layers']}
        current=source.source_addresses['animated_registration_sha256']
    result.update(schema='autospine.binding-policy-overview/v1',project_id=project,active_decision_sha256=None)
    for row in result['rows']:row['name']=names[row['layer_id']]
    _,entry=_registrations(store,project)[-1]
    try:folder=_folder(store.state_root,entry['manifest']['dataset_id'],KIND)
    except ValueError:return result
    for path in sorted(folder.glob('*.json')):
        try:doc,_=read_decision(store,project,path.stem)
        except ValueError:continue
        if doc['after_registration_sha256']==current:
            result['active_decision_sha256']=path.stem
            break
    return result


def dispatch(tail,handler,method,project):
    from .animated_routes import manager_for
    from .web_routes import _error, _require_mutation
    allowed='GET, HEAD, POST, OPTIONS'
    if tail:
        _error(handler,404,'pipeline_route_not_found');return True
    if method=='OPTIONS' or method not in allowed.split(', '):
        handler._send_bytes(204 if method=='OPTIONS' else 405,b'','application/json',
                            extra_headers={'Allow':allowed},visual_review=True);return True
    try:
        store=manager_for(handler.server).application.projects
        operation=None
        if method=='POST':
            _require_mutation(handler.headers)
            body=read_json_object_request(handler,maximum_bytes=2048)
            keys={'action','expected_resolved_sha256','expected_input_sha256'}
            if body.get('action')=='undo':keys.add('decision_sha256')
            if set(body)!=keys or body.get('action') not in ('apply','undo'):
                raise ValueError('invalid policy request')
            for key in keys-{'action'}:require_sha256(body[key],key)
            with load_inputs(store,project) as source:
                if (source.source_addresses['resolved_project_sha256']!=body['expected_resolved_sha256'] or
                        source.source_addresses['input_identity_sha256']!=body['expected_input_sha256']):
                    raise AnimatedSourceError('animated_review_conflict')
            operation=apply(store,project,body['expected_input_sha256']) if body['action']=='apply' else \
                undo(store,project,body['decision_sha256'],body['expected_input_sha256'])
        result=overview(store,project)
        if operation is not None:result['operation']=operation
        handler._send_visual_json(200,result)
    except HttpJsonRequestError as exc:_error(handler,exc.status,exc.code)
    except (ValueError,OSError,RuntimeError,TypeError,KeyError) as exc:
        reason=getattr(exc,'reason_code','binding_policy_request_failed')
        _error(handler,403 if reason in ('forbidden_origin','forbidden_intent') else
               409 if reason in ('animated_review_conflict','animated_source_stale') else 400,reason)
    return True
