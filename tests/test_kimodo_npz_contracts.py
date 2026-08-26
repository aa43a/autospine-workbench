"""Schema and semantic gates for formal Kimodo NPZ source metadata."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_map_validation import (  # noqa: E402
    KimodoNpzMapError,
    kimodo_npz_map_sha256,
    require_kimodo_npz_map,
)
from autospine_workbench.kimodo_npz_source import (  # noqa: E402
    KimodoNpzSourceError,
    expected_array_names,
    expected_contact_count,
    kimodo_npz_source_sha256,
    require_kimodo_npz_source,
)
from autospine_workbench.kimodo_soma77 import (  # noqa: E402
    SOMA77_DEFINITION_SHA256,
    SOMA77_JOINT_NAMES,
    SOMA77_PARENT_INDICES,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


class KimodoNpzContractTests(unittest.TestCase):
    def test_pinned_soma77_identity_is_complete_and_stable(self):
        self.assertEqual(77, len(SOMA77_JOINT_NAMES))
        self.assertEqual(77, len(SOMA77_PARENT_INDICES))
        self.assertEqual(None, SOMA77_PARENT_INDICES[0])
        self.assertEqual(77, len(set(SOMA77_JOINT_NAMES)))
        self.assertEqual(
            "081e13564aed36abcbbc53df655d40e6ba5141023452b78f07a96409e71d8623",
            SOMA77_DEFINITION_SHA256,
        )

    def test_source_schema_semantics_raw_binding_and_inventory(self):
        raw = b"exact raw bytes"
        source = source_document(raw, recorded=True)
        require_kimodo_npz_source(source, raw_npz=raw)
        self.assertEqual(7, len(expected_array_names(source)))
        self.assertEqual(4, expected_contact_count(source))
        self.assertEqual(
            kimodo_npz_source_sha256(source),
            kimodo_npz_source_sha256(deepcopy(source)),
        )
        self._schema("kimodo-npz-source-v1.schema.json", source)

        core = source_document(raw, inventory="core-v1")
        require_kimodo_npz_source(core, raw_npz=raw)
        self.assertEqual(5, len(expected_array_names(core)))

    def test_source_rejects_implicit_or_drifting_interpretation(self):
        raw = b"exact raw bytes"
        baseline = source_document(raw)
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["raw_npz"].update(frame_count=1),
            lambda value: value["raw_npz"].update(
                frames_per_second={"numerator": 30.0, "denominator": 1}
            ),
            lambda value: value["skeleton"].update(joint_count=30),
            lambda value: value["skeleton"].update(definition_sha256="0" * 64),
            lambda value: value["coordinate_system"].update(up_axis="+Z"),
            lambda value: value["array_profile"].update(float_dtype="=f4"),
            lambda value: value["array_profile"].update(contact_dtype="|O"),
            lambda value: value["producer"].update(status="latest"),
        )
        for mutate in mutations:
            candidate = deepcopy(baseline)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                KimodoNpzSourceError
            ):
                require_kimodo_npz_source(candidate)
        for changed in (raw + b"\n", b""):
            with self.subTest(raw=changed), self.assertRaises(KimodoNpzSourceError):
                require_kimodo_npz_source(baseline, raw_npz=changed)

    def test_map_schema_semantics_and_source_cross_binding(self):
        source = source_document()
        mapping = map_document()
        require_kimodo_npz_map(mapping, source=source)
        self.assertEqual(
            kimodo_npz_map_sha256(mapping),
            kimodo_npz_map_sha256(deepcopy(mapping)),
        )
        self._schema("kimodo-npz-map-v1.schema.json", mapping)

        six_source = source_document(
            contact_layout=
                "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
        )
        six_map = map_document(
            contact_layout=
                "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
        )
        require_kimodo_npz_map(six_map, source=six_source)

    def test_map_rejects_role_topology_contact_and_basis_guessing(self):
        source = source_document()
        baseline = map_document()
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["basis"].update(screen_y="+X"),
            lambda value: value["root"].update(position_source="smooth_root_pos"),
            lambda value: value["bones"].reverse(),
            lambda value: value["bones"][1].update(joint_name="LeftArm"),
            lambda value: value["bones"][1].update(aim_joint_name="Hips"),
            lambda value: value["contact"]["channels"][0].update(index=1),
            lambda value: value["contact"].update(layout=
                "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"),
        )
        for mutate in mutations:
            candidate = deepcopy(baseline)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                KimodoNpzMapError
            ):
                require_kimodo_npz_map(candidate, source=source)

        six_source = source_document(
            contact_layout=
                "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
        )
        with self.assertRaisesRegex(KimodoNpzMapError, "differs from source"):
            require_kimodo_npz_map(baseline, source=six_source)

    def test_every_semantic_change_changes_its_canonical_identity(self):
        source = source_document()
        mapping = map_document()
        changed_source = deepcopy(source)
        changed_source["raw_npz"]["frames_per_second"]["numerator"] = 60
        changed_map = deepcopy(mapping)
        changed_map["root"]["reference_length_meters"] = 2.0
        self.assertNotEqual(
            kimodo_npz_source_sha256(source),
            kimodo_npz_source_sha256(changed_source),
        )
        self.assertNotEqual(
            kimodo_npz_map_sha256(mapping),
            kimodo_npz_map_sha256(changed_map),
        )

    def _schema(self, name: str, value: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
