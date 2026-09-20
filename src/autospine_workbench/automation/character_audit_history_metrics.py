"""Historical human flags survive replacement of the automatic binding they assessed."""
from .character_audit_continuity import identity, verified_proof


def summarize(job, value):
    from .character_auto_audit import inventory
    proof = verified_proof(job, value)
    if proof is None:
        return None
    assessed = set()
    flagged = set()
    for history in proof['histories']:
        rows = {row['layer_id']: identity(row) for row in inventory(history['job'])}
        for entry in history['entries']:
            for layer, verdict in entry['review']['reviews'].items():
                if verdict in {'correct', 'incorrect'}:
                    assessed.add(rows[layer])
                if verdict == 'incorrect':
                    flagged.add(rows[layer])
    current = {identity(row) for row in inventory(job)}
    return dict(scope='project_recorded_automatic_decision_history',
                assessed_decisions=len(assessed), ever_flagged_decisions=len(flagged),
                flagged_decisions_no_longer_current=len(flagged-current),
                # A flag can be withdrawn as a false positive; replacement is not repair acceptance.
                population_error_rate=None, repaired_decisions=None)
