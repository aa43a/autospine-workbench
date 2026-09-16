"""Extend an exact final exclusion batch without replacing prior confirmations."""
from hashlib import sha256
from ..resolved_project import canonical_sha256
from ..targets.character43.final_region_exclusion import apply_batch
from .pipeline_run import PipelineRunError


def source(store, current, rendered, *, after_components=False):
    if not current['active']:
        raise PipelineRunError('character_final_append_requires_active_review')
    review=current['review']
    original=store.read(review['source_bundle_sha256'])
    expected=apply_batch(original,review['decisions'],after_components=after_components)
    # Full-byte equality also protects transformed geometry, textures and recipe evidence.
    if expected != rendered:
        raise PipelineRunError('character_final_append_source_changed')
    digest=canonical_sha256({n:sha256(raw).hexdigest() for n,raw in original.items()})
    if digest!=review['source_bundle_sha256']:
        raise PipelineRunError('character_final_append_source_changed')
    return original,digest,list(review['decisions'])
