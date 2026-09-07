"""Explicit preview target versions, independently pinned from certification."""

DEFAULT_TARGET_VERSION = "4.3.26"
LEGACY_TARGET_VERSION = "4.2"
_ENGINES = {
    LEGACY_TARGET_VERSION: "region-spine-preview-v1",
    DEFAULT_TARGET_VERSION: "region-spine-preview-spine43-4.3.26-v1",
}


def require_target_version(value):
    if type(value) is not str or value not in _ENGINES:
        from .pipeline_run import PipelineRunError

        raise PipelineRunError("unsupported_target_version")
    return value


def engine_for_target(value):
    return _ENGINES[require_target_version(value)]


def target_from_run(run):
    if type(run) is dict:
        for version, engine in _ENGINES.items():
            if run.get("engine") == engine:
                return version
    from .pipeline_run import PipelineRunError

    raise PipelineRunError("unsupported_target_version")
