"""Local, dependency-free backend for the AutoSpine workbench."""

from .contracts import (
    LAYER_SCHEMA_VERSION,
    OVERRIDE_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    SKELETON_SCHEMA_VERSION,
)
from .project_store import ProjectStore

__all__ = [
    "LAYER_SCHEMA_VERSION",
    "OVERRIDE_SCHEMA_VERSION",
    "PROJECT_SCHEMA_VERSION",
    "SKELETON_SCHEMA_VERSION",
    "ProjectStore",
]

__version__ = "0.1.0"
