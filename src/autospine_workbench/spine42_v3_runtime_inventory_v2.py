"""Pure declared-inventory validation for runtime v2; no reader authority."""

from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_v3_runtime_evidence_contract_v2 import MANIFEST_NAME, safe_png
from .spine42_v3_runtime_profile import MAX_CAPTURE_ARTIFACTS


def declared_artifacts(raw, error_type):
    try:
        rows = strict_json_object(raw, MANIFEST_NAME)["artifacts"]
        fields = {
            "artifact_id", "logical_path", "stored_path", "kind",
            "case_id", "sha256", "size_bytes",
        }
        if type(rows) is not list or not 1 <= len(rows) <= MAX_CAPTURE_ARTIFACTS:
            raise error_type(
                "Declared runtime capture v2 count is invalid")
        for row in rows:
            logical = row.get("logical_path") if type(row) is dict else None
            if type(row) is not dict or set(row) != fields \
                    or not safe_png(logical) \
                    or row.get("stored_path") != f"captures/{logical}" \
                    or type(row.get("artifact_id")) is not str:
                raise error_type(
                    "Declared runtime capture v2 path is unsafe")
        for field in ("artifact_id", "logical_path", "stored_path"):
            values = [row[field].casefold() for row in rows]
            if len(values) != len(set(values)):
                raise error_type(
                    "Declared runtime captures v2 contain an alias")
        return rows
    except error_type:
        raise
    except (KeyError, SafeInputFileError, TypeError, ValueError) as exc:
        raise error_type(
            "Declared runtime capture v2 inventory is malformed") from exc
