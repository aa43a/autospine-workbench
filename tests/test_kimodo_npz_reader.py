"""Archive security and snapshot identity tests for formal Kimodo NPZ."""

from __future__ import annotations

from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_reader import (  # noqa: E402
    KimodoNpzReaderError,
    decode_kimodo_npz,
    read_kimodo_npz,
)
from autospine_workbench.safe_input_files import SafeInputFileError  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npy,
    build_npz,
    float_payload,
    member_bytes,
)
from tests.kimodo_npz_helpers import source_document  # noqa: E402


class KimodoNpzReaderTests(unittest.TestCase):
    def test_stored_deflated_core_complete_and_contact_layouts_decode(self):
        cases = (
            ("core-v1", 4, zipfile.ZIP_STORED),
            ("complete-v1", 4, zipfile.ZIP_DEFLATED),
            ("complete-v1", 6, zipfile.ZIP_STORED),
        )
        for inventory, contacts, compression in cases:
            layout = (
                "left-heel-toe-right-heel-toe-v1" if contacts == 4 else
                "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
            )
            raw = build_npz(
                member_bytes(inventory=inventory, contacts=contacts),
                compression=compression,
            )
            source = source_document(
                raw, inventory=inventory, contact_layout=layout
            )
            first = decode_kimodo_npz(raw, source)
            second = decode_kimodo_npz(raw, deepcopy(source))
            self.assertEqual(first, second)
            self.assertEqual(raw, first.raw_npz)
            self.assertEqual(3, first.frame_count)
            self.assertEqual(
                5 if inventory == "core-v1" else 7, len(first.inventory)
            )
            self.assertEqual(contacts, first.arrays["foot_contacts"].shape[1])

    def test_real_file_is_read_once_then_bound_to_source(self):
        raw = build_npz()
        source = source_document(raw)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "motion.npz"
            path.write_bytes(raw)
            loaded = read_kimodo_npz(path, source)
            self.assertEqual(raw, loaded.raw_npz)
        with patch(
            "autospine_workbench.kimodo_npz_reader.read_real_file",
            side_effect=SafeInputFileError("alias"),
        ), self.assertRaisesRegex(KimodoNpzReaderError, "safely read"):
            read_kimodo_npz(Path("unused"), source)

    def test_source_dtype_shape_and_raw_identity_drift_fail(self):
        raw = build_npz()
        source = source_document(raw)
        for mutate in (
            lambda value: value["raw_npz"].update(frame_count=4),
            lambda value: value["array_profile"].update(inventory="core-v1"),
            lambda value: value["array_profile"].update(
                contact_layout=
                    "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
            ),
        ):
            changed = deepcopy(source)
            mutate(changed)
            with self.subTest(source=changed), self.assertRaises(KimodoNpzReaderError):
                decode_kimodo_npz(raw, changed)
        changed_raw = raw + b"\x00"
        with self.assertRaises(KimodoNpzReaderError):
            decode_kimodo_npz(changed_raw, source)

    def test_missing_extra_duplicate_case_and_path_members_fail(self):
        baseline = member_bytes()
        variants = []
        missing = dict(baseline)
        missing.pop("root_positions.npy")
        variants.append(missing)
        extra = dict(baseline)
        extra["extra.npy"] = next(iter(extra.values()))
        variants.append(extra)
        case = dict(baseline)
        case["ROOT_POSITIONS.npy"] = case.pop("root_positions.npy")
        variants.append(case)
        path = dict(baseline)
        path["../root_positions.npy"] = path.pop("root_positions.npy")
        variants.append(path)
        for members in variants:
            raw = build_npz(members)
            with self.subTest(names=tuple(members)), self.assertRaises(
                KimodoNpzReaderError
            ):
                decode_kimodo_npz(raw, source_document(raw))

        output = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(output, "w") as archive:
                for name, data in baseline.items():
                    archive.writestr(name, data)
                archive.writestr(
                    "root_positions.npy", baseline["root_positions.npy"]
                )
        duplicate = output.getvalue()
        with self.assertRaises(KimodoNpzReaderError):
            decode_kimodo_npz(duplicate, source_document(duplicate))

    def test_archive_metadata_compression_and_budgets_fail_closed(self):
        cases = (
            build_npz(archive_comment=b"comment"),
            build_npz(member_comment=b"comment"),
            build_npz(compression=zipfile.ZIP_BZIP2),
        )
        for raw in cases:
            with self.subTest(size=len(raw)), self.assertRaises(KimodoNpzReaderError):
                decode_kimodo_npz(raw, source_document(raw))
        raw = build_npz()
        with patch(
            "autospine_workbench.kimodo_npz_reader.MAX_TOTAL_UNCOMPRESSED_BYTES", 1
        ), self.assertRaisesRegex(KimodoNpzReaderError, "budget"):
            decode_kimodo_npz(raw, source_document(raw))

    def test_encrypted_flag_crc_corruption_and_truncation_fail_closed(self):
        raw = build_npz()
        encrypted = bytearray(raw)
        for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            cursor = 0
            while True:
                cursor = encrypted.find(signature, cursor)
                if cursor < 0:
                    break
                flags = int.from_bytes(
                    encrypted[cursor + flag_offset:cursor + flag_offset + 2],
                    "little",
                ) | 1
                encrypted[cursor + flag_offset:cursor + flag_offset + 2] = \
                    flags.to_bytes(2, "little")
                cursor += 4

        corrupted = bytearray(raw)
        local = corrupted.find(b"PK\x03\x04")
        name_length = int.from_bytes(corrupted[local + 26:local + 28], "little")
        extra_length = int.from_bytes(corrupted[local + 28:local + 30], "little")
        payload = local + 30 + name_length + extra_length
        corrupted[payload] ^= 1

        for candidate in (bytes(encrypted), bytes(corrupted), raw[:-20]):
            with self.subTest(size=len(candidate)), self.assertRaises(
                KimodoNpzReaderError
            ):
                decode_kimodo_npz(candidate, source_document(candidate))

    def test_unsafe_npy_payload_is_rejected_inside_archive(self):
        members = member_bytes()
        shape = (3, 77, 3)
        members["posed_joints.npy"] = build_npy(
            "|O", shape, float_payload(shape)
        )
        raw = build_npz(members)
        with self.assertRaises(KimodoNpzReaderError):
            decode_kimodo_npz(raw, source_document(raw))


if __name__ == "__main__":
    unittest.main()
