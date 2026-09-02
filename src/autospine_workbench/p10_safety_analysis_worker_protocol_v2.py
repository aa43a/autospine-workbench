"""Strict bounded JSONL protocol for the isolated P10.4b v2 worker."""

from __future__ import annotations

import json
import re

from .p10_safety_analysis_job_files_v2 import require_run_id
from .p10_safety_analysis_job_validation_v2 import require_result_address


PROTOCOL = "autospine-p10-safety-analysis-worker/v2"
MAX_LINE_BYTES = 4096
MAX_MESSAGE_COUNT = 4096
MAX_STDOUT_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
STAGES = (
    "review_admission", "exact_source", "amplitude_probes",
    "continuous_boxes", "continuous_validation", "current_head_recheck",
)
_FAILURE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_COMMON = {"protocol", "sequence", "type", "run_id", "job_id"}


class P10SafetyAnalysisWorkerProtocolV2Error(ValueError):
    """Raised when one worker message or stream transition is invalid."""


class P10SafetyAnalysisWorkerEmitterV2:
    """Write canonical JSONL messages to one binary stream."""

    def __init__(self, stream, run_id: str, job_id: str) -> None:
        require_run_id(run_id)
        require_run_id(job_id)
        if not callable(getattr(stream, "write", None)):
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol stream is invalid"
            )
        self._stream = stream
        self.run_id, self.job_id = run_id, job_id
        self._sequence = 0
        self._terminal = False

    def started(self) -> None:
        self._emit("started", {})

    def progress(self, stage: str, current: int, total: int) -> None:
        self._emit("progress", {
            "stage": stage, "current": current, "total": total,
        })

    def result(self, result) -> None:
        self._emit("result", {"result": require_result_address(result)})
        self._terminal = True

    def failure(self, failure_code: str, terminal: bool) -> None:
        self._emit("failure", {
            "failure_code": failure_code, "terminal": terminal,
        })
        self._terminal = True

    def _emit(self, kind, fields) -> None:
        if self._terminal:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol already reached a terminal message"
            )
        self._sequence += 1
        value = {
            "protocol": PROTOCOL, "sequence": self._sequence,
            "type": kind, "run_id": self.run_id, "job_id": self.job_id,
            **fields,
        }
        raw = _canonical(value) + b"\n"
        if len(raw) > MAX_LINE_BYTES:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol message is excessive"
            )
        self._stream.write(raw)
        flush = getattr(self._stream, "flush", None)
        if callable(flush):
            flush()


class P10SafetyAnalysisWorkerDecoderV2:
    """Validate exact identities, stages, progress, and terminal ordering."""

    def __init__(self, run_id: str, job_id: str) -> None:
        require_run_id(run_id)
        require_run_id(job_id)
        self.run_id, self.job_id = run_id, job_id
        self.sequence = 0
        self.terminal_message = None
        self._stage_index = -1
        self._stage_progress = None

    def accept(self, raw_line: bytes):
        if type(raw_line) is not bytes or not 0 < len(raw_line) <= MAX_LINE_BYTES:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol line size is invalid"
            )
        try:
            value = json.loads(
                raw_line.decode("utf-8"), object_pairs_hook=_unique_object,
            )
            if not isinstance(value, dict) or _canonical(value) != raw_line:
                raise ValueError("canonical")
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol line is not canonical JSON"
            ) from exc
        if self.terminal_message is not None:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol contains data after its terminal message"
            )
        self._common(value)
        kind = value["type"]
        if kind == "started":
            self._started(value)
        elif kind == "progress":
            self._progress(value)
        elif kind == "result":
            self._result(value)
        elif kind == "failure":
            self._failure(value)
        else:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol message type is unsupported"
            )
        self.sequence += 1
        return value

    def _common(self, value) -> None:
        if value.get("protocol") != PROTOCOL \
                or value.get("run_id") != self.run_id \
                or value.get("job_id") != self.job_id \
                or type(value.get("sequence")) is not int \
                or value["sequence"] != self.sequence + 1 \
                or value["sequence"] > MAX_MESSAGE_COUNT:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol identity or sequence differs"
            )

    def _started(self, value) -> None:
        if set(value) != _COMMON or self.sequence != 0:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker protocol start message is invalid"
            )

    def _progress(self, value) -> None:
        fields = _COMMON | {"stage", "current", "total"}
        stage = value.get("stage")
        current, total = value.get("current"), value.get("total")
        if set(value) != fields or self.sequence == 0 or stage not in STAGES \
                or type(current) is not int or type(total) is not int \
                or not 0 <= current <= total \
                or not 1 <= total <= 1_000_000:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker progress message is invalid"
            )
        index = STAGES.index(stage)
        if index == self._stage_index:
            previous, previous_total = self._stage_progress
            valid = total == previous_total and current >= previous
        else:
            valid = index == self._stage_index + 1 \
                and (self._stage_progress is None \
                     or self._stage_progress[0] == self._stage_progress[1])
        if not valid:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker progress stage ordering is invalid"
            )
        self._stage_index = index
        self._stage_progress = (current, total)

    def _result(self, value) -> None:
        if set(value) != _COMMON | {"result"} \
                or self._stage_index != len(STAGES) - 1 \
                or self._stage_progress is None \
                or self._stage_progress[0] != self._stage_progress[1]:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker result arrived before complete progress"
            )
        try:
            value["result"] = require_result_address(value["result"])
        except Exception as exc:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker result metadata is invalid"
            ) from exc
        self.terminal_message = value

    def _failure(self, value) -> None:
        code, terminal = value.get("failure_code"), value.get("terminal")
        if set(value) != _COMMON | {"failure_code", "terminal"} \
                or self.sequence == 0 or type(code) is not str \
                or _FAILURE.fullmatch(code) is None \
                or type(terminal) is not bool:
            raise P10SafetyAnalysisWorkerProtocolV2Error(
                "Worker failure message is invalid"
            )
        self.terminal_message = value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "MAX_LINE_BYTES", "MAX_MESSAGE_COUNT", "MAX_STDERR_BYTES",
    "MAX_STDOUT_BYTES", "PROTOCOL", "STAGES",
    "P10SafetyAnalysisWorkerDecoderV2",
    "P10SafetyAnalysisWorkerEmitterV2",
    "P10SafetyAnalysisWorkerProtocolV2Error",
]
