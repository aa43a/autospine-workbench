"""Shared public error for P10.4b v2 asynchronous management."""


class P10SafetyAnalysisManagerV2Error(RuntimeError):
    """Raised when an async safety-analysis run cannot be managed safely."""


__all__ = ["P10SafetyAnalysisManagerV2Error"]
