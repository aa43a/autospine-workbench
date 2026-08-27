"""Strict static preparation for P10.5d body-sway seam locators.

The result is detached setup data for a later interval pose evaluator.  This
module deliberately makes no dynamic-safety, visual, runtime, or release claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .body_sway_dynamic_seam_moments import (
    FractionPoint,
    PreparedDynamicSeamInfluence,
    PreparedDynamicSeamMoment,
    PreparedDynamicSeamVertex,
    prepare_dynamic_seam_moments,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    PreparedBodySwayMesh,
    PreparedBodySwayRegion,
)
from .mesh_skinning_prepared import PreparedSkinningRig
from .body_sway_dynamic_seam_locator_fields import (
    bind_dynamic_seam_geometry,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_validation import (
    require_reviewed_seam_anchor_set,
    reviewed_seam_anchor_set_sha256,
)
from .seam_anchor_locators import (
    MESH_QUANTIZATION,
    resolve_attachment_locator_exact,
)


_Q4096_HALF_STEP = Fraction(1, 8192)


class BodySwayDynamicSeamLocatorError(ValueError):
    """Raised when static seam data cannot bind the exact prepared RigIR."""


@dataclass(frozen=True, slots=True)
class PreparedBodySwayDynamicSeamLocator:
    attachment_id: str
    attachment_type: str
    slot_id: str
    slot_bone_id: str
    setup_canvas_xy: FractionPoint
    vertices: tuple[PreparedDynamicSeamVertex, ...]
    moments: tuple[PreparedDynamicSeamMoment, ...]


@dataclass(frozen=True, slots=True)
class PreparedBodySwayDynamicSeamPair:
    pair_id: str
    parent: PreparedBodySwayDynamicSeamLocator
    child: PreparedBodySwayDynamicSeamLocator


@dataclass(frozen=True, slots=True)
class PreparedBodySwayDynamicSeamRelationship:
    relationship_id: str
    anchors: tuple[PreparedBodySwayDynamicSeamPair, ...]


@dataclass(frozen=True, slots=True)
class PreparedBodySwayDynamicSeamLocatorSet:
    project_id: str
    p3_rig_sha256: str
    reviewed_seam_anchor_set_sha256: str
    relationships: tuple[PreparedBodySwayDynamicSeamRelationship, ...]
    _rig: PreparedSkinningRig = field(repr=False, compare=False)


def prepare_body_sway_dynamic_seam_locators(
    rig: Mapping[str, Any],
    context: PreparedBodySwayGeometryContext,
    reviewed_set: Mapping[str, Any],
) -> PreparedBodySwayDynamicSeamLocatorSet:
    """Cross-bind exact RigIR, prepared geometry, and all reviewed locators."""

    try:
        if not isinstance(rig, Mapping):
            raise BodySwayDynamicSeamLocatorError("RigIR must be an object")
        if type(context) is not PreparedBodySwayGeometryContext:
            raise BodySwayDynamicSeamLocatorError(
                "Prepared body-sway geometry context is invalid"
            )
        require_reviewed_seam_anchor_set(reviewed_set)
        rig_sha = canonical_sha256(rig)
        if rig_sha != reviewed_set["source"]["p3_rig_sha256"]:
            raise BodySwayDynamicSeamLocatorError(
                "Reviewed seam anchor set binds a different P3 RigIR"
            )
        attachments = bind_dynamic_seam_geometry(rig, context)
        relationships = tuple(
            _prepare_relationship(row, attachments, context)
            for row in reviewed_set["relationships"]
        )
        return PreparedBodySwayDynamicSeamLocatorSet(
            project_id=reviewed_set["project_id"],
            p3_rig_sha256=rig_sha,
            reviewed_seam_anchor_set_sha256=
                reviewed_seam_anchor_set_sha256(reviewed_set),
            relationships=relationships,
            _rig=context.skinning_rig,
        )
    except BodySwayDynamicSeamLocatorError:
        raise
    except (
        AttributeError, IndexError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamLocatorError(
            f"Dynamic seam locator preparation failed: {exc}"
        ) from exc


def resolve_prepared_dynamic_seam_setup_exact(
    locator: PreparedBodySwayDynamicSeamLocator,
) -> FractionPoint:
    """Resolve retained vertex terms without accessing the source attachment."""

    if type(locator) is not PreparedBodySwayDynamicSeamLocator:
        raise BodySwayDynamicSeamLocatorError(
            "Prepared dynamic seam locator is invalid"
        )
    return tuple(sum(
        vertex.locator_weight * vertex.setup_canvas_xy[axis]
        for vertex in locator.vertices
    ) for axis in range(2))  # type: ignore[return-value]


def _prepare_relationship(row, attachments, context):
    first = row["anchors"][0]
    kinds = first["parent"]["attachment_type"], first["child"]["attachment_type"]
    if kinds == ("mesh", "mesh"):
        raise BodySwayDynamicSeamLocatorError(
            "Mesh-mesh dynamic seam locators are unsupported in v1"
        )
    anchors = tuple(
        PreparedBodySwayDynamicSeamPair(
            pair["pair_id"],
            _prepare_locator(pair["parent"], attachments, context),
            _prepare_locator(pair["child"], attachments, context),
        )
        for pair in row["anchors"]
    )
    return PreparedBodySwayDynamicSeamRelationship(
        row["relationship_id"], anchors
    )


def _prepare_locator(locator, attachments, context):
    identifier = locator["attachment_id"]
    if identifier not in attachments:
        raise BodySwayDynamicSeamLocatorError(
            f"Reviewed locator references missing attachment: {identifier}"
        )
    original, prepared = attachments[identifier]
    resolved = resolve_attachment_locator_exact(locator, original)
    if type(prepared) is PreparedBodySwayRegion:
        influence_rows = prepared.binding._influences[0]
        vertices = (_vertex(None, Fraction(1), resolved, influence_rows, context),)
    elif type(prepared) is PreparedBodySwayMesh:
        indices = tuple(locator["vertex_indices"])
        weights = tuple(Fraction(value, MESH_QUANTIZATION)
                        for value in locator["weights_q65535"])
        vertices = tuple(_vertex(
            index, weight,
            tuple(Fraction.from_float(value)
                  for value in prepared.binding._vertices[index]),
            prepared.binding._influences[index], context,
        ) for index, weight in zip(indices, weights, strict=True))
    else:
        raise BodySwayDynamicSeamLocatorError(
            "Prepared dynamic seam attachment is invalid"
        )
    result = PreparedBodySwayDynamicSeamLocator(
        identifier, prepared.attachment_type, prepared.slot_id,
        prepared.slot_bone_id, resolved, vertices,
        prepare_dynamic_seam_moments(vertices),
    )
    dynamic_setup = resolve_prepared_dynamic_seam_setup_exact(result)
    if type(prepared) is PreparedBodySwayRegion:
        if dynamic_setup != resolved:
            raise BodySwayDynamicSeamLocatorError(
                f"Prepared region locator setup point differs: {identifier}"
            )
    elif any(abs(dynamic - static) > _Q4096_HALF_STEP
             for dynamic, static in zip(dynamic_setup, resolved, strict=True)):
        raise BodySwayDynamicSeamLocatorError(
            f"Prepared mesh locator exceeds Q4096 setup tolerance: {identifier}"
        )
    return result


def _vertex(index, locator_weight, point, rows, context):
    influences = tuple(
        PreparedDynamicSeamInfluence(
            bone_index, context.skinning_rig._bones[bone_index].identifier,
            Fraction.from_float(weight),
        ) for bone_index, weight in rows
    )
    return PreparedDynamicSeamVertex(
        index, locator_weight, point, influences
    )
