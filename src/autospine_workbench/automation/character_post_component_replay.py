"""Reuse the bounded review resolver for the final post-component exclusion."""
from .character_component_replay import derive as component_replay


def derive(manager,result,files):
    return component_replay(manager,result,files,after_components=True)
