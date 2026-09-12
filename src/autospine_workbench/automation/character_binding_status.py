"""Binding completion follows the decision action, not who last edited notes."""


def needs_review(layer, confirmed=()):
    state = layer.get('state'); decision = layer.get('binding_decision') or {}
    source = decision.get('decision_source'); action = decision.get('action')
    if state == 'not_visible': return False
    if source == 'policy_auto' and decision.get('evidence_current') is not True: return True
    if state == 'excluded': return action != 'exclude' or source not in {'explicit_selection', 'legacy_selection', 'policy_auto'}
    if state not in {'weighted_candidate', 'rigid_reviewed'}: return True
    if state == 'weighted_candidate' and action == 'pending' and layer['layer_id'] in confirmed: return False
    return (action != 'bind' or type(decision.get('option_id')) is not str or not decision['option_id']
            or source not in {'explicit_selection', 'legacy_selection', 'policy_auto'})
