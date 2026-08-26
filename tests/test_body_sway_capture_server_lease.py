"""Lifecycle tests for the non-daemon loopback capture server lease."""

from __future__ import annotations

from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_capture_server_lease import (  # noqa: E402
    BodySwayCaptureServerLease,
    BodySwayCaptureServerLeaseError,
)


class _HealthyServer:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.closed = False

    def serve_forever(self, *, poll_interval: float) -> None:
        self.stop.wait(5)

    def shutdown(self) -> None:
        self.stop.set()

    def server_close(self) -> None:
        self.closed = True


class _FailingServer(_HealthyServer):
    def serve_forever(self, *, poll_interval: float) -> None:
        raise OSError("serve failed")


class _ReturningServer(_HealthyServer):
    def serve_forever(self, *, poll_interval: float) -> None:
        return


class _ShutdownOnceServer(_HealthyServer):
    def __init__(self) -> None:
        super().__init__()
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        if self.shutdown_calls == 1:
            raise OSError("shutdown failed")
        super().shutdown()


class _DelayedStopServer(_ShutdownOnceServer):
    def shutdown(self) -> None:
        self.shutdown_calls += 1
        if self.shutdown_calls > 1:
            self.stop.set()


class _CloseOnceServer(_HealthyServer):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    def server_close(self) -> None:
        self.close_calls += 1
        if self.close_calls == 1:
            raise OSError("close failed")
        super().server_close()


class _CloseReleasesAfterPermanentShutdownFailure(_HealthyServer):
    def __init__(self) -> None:
        super().__init__()
        self.shutdown_calls = 0
        self.close_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        raise OSError("permanent shutdown failure")

    def server_close(self) -> None:
        self.close_calls += 1
        self.closed = True
        self.stop.set()


class _NeverStopsServer(_CloseReleasesAfterPermanentShutdownFailure):
    def server_close(self) -> None:
        self.close_calls += 1
        self.closed = True


class BodySwayCaptureServerLeaseTests(unittest.TestCase):
    def test_healthy_server_is_non_daemon_and_closed_before_return(self):
        server = _HealthyServer()
        lease = BodySwayCaptureServerLease(server)
        self.assertFalse(lease.is_daemon)
        with lease:
            lease.require_healthy()
            self.assertFalse(server.closed)
        self.assertTrue(server.closed)

    def test_serve_failure_is_reported_and_socket_is_closed(self):
        server = _FailingServer()
        with self.assertRaisesRegex(
            BodySwayCaptureServerLeaseError, "server failed|stopped"
        ):
            with BodySwayCaptureServerLease(server):
                pass
        self.assertTrue(server.closed)

    def test_clean_early_return_is_failure_and_socket_is_closed(self):
        server = _ReturningServer()
        with self.assertRaisesRegex(
            BodySwayCaptureServerLeaseError, "returned|stopped"
        ):
            with BodySwayCaptureServerLease(server):
                pass
        self.assertTrue(server.closed)

    def test_thread_start_failure_still_closes_bound_socket(self):
        server = _HealthyServer()
        lease = BodySwayCaptureServerLease(server)
        with patch.object(
            lease._thread, "start", side_effect=RuntimeError("no thread")
        ), self.assertRaisesRegex(
            BodySwayCaptureServerLeaseError, "could not start"
        ):
            with lease:
                pass
        self.assertTrue(server.closed)

    def test_shutdown_failure_is_visible_and_second_close_recovers(self):
        server = _ShutdownOnceServer()
        lease = BodySwayCaptureServerLease(server)
        lease.__enter__()
        try:
            with patch(
                "autospine_workbench.body_sway_capture_server_lease."
                "STOP_TIMEOUT_SECONDS", 0.01,
            ), self.assertRaisesRegex(
                BodySwayCaptureServerLeaseError, "shutdown failed"
            ):
                lease.close()
            self.assertTrue(lease._thread.is_alive())
            lease.close()
            self.assertFalse(lease._thread.is_alive())
        finally:
            server.stop.set()
            lease._thread.join(1)

    def test_join_timeout_is_visible_and_second_close_recovers(self):
        server = _DelayedStopServer()
        lease = BodySwayCaptureServerLease(server)
        lease.__enter__()
        try:
            with patch(
                "autospine_workbench.body_sway_capture_server_lease."
                "STOP_TIMEOUT_SECONDS", 0.01,
            ), self.assertRaisesRegex(
                BodySwayCaptureServerLeaseError, "did not stop"
            ):
                lease.close()
            lease.close()
            self.assertFalse(lease._thread.is_alive())
        finally:
            server.stop.set()
            lease._thread.join(1)

    def test_server_close_failure_is_visible_and_retryable(self):
        server = _CloseOnceServer()
        lease = BodySwayCaptureServerLease(server)
        lease.__enter__()
        with self.assertRaisesRegex(
            BodySwayCaptureServerLeaseError, "close failed"
        ):
            lease.close()
        self.assertFalse(lease._thread.is_alive())
        lease.close()
        self.assertTrue(server.closed)

    def test_primary_error_is_preserved_and_cleanup_failure_is_noted(self):
        server = _CloseOnceServer()
        lease = BodySwayCaptureServerLease(server)
        primary = LookupError("capture failed")
        with self.assertRaises(LookupError) as raised:
            with lease:
                raise primary
        self.assertIs(primary, raised.exception)
        self.assertTrue(any(
            "cleanup also failed" in note
            for note in getattr(primary, "__notes__", ())
        ))
        self.assertTrue(server.closed)
        self.assertFalse(lease._thread.is_alive())

    def test_primary_error_survives_retryable_shutdown_failure(self):
        server = _ShutdownOnceServer()
        lease = BodySwayCaptureServerLease(server)
        primary = LookupError("capture failed")
        with patch(
            "autospine_workbench.body_sway_capture_server_lease."
            "STOP_TIMEOUT_SECONDS", 0.01,
        ), self.assertRaises(LookupError) as raised:
            with lease:
                raise primary
        self.assertIs(primary, raised.exception)
        self.assertTrue(getattr(primary, "__notes__", ()))
        self.assertTrue(server.closed)
        self.assertFalse(lease._thread.is_alive())

    def test_socket_close_fallback_releases_permanent_shutdown_failure(self):
        server = _CloseReleasesAfterPermanentShutdownFailure()
        lease = BodySwayCaptureServerLease(server)
        lease.__enter__()
        with patch(
            "autospine_workbench.body_sway_capture_server_lease."
            "STOP_TIMEOUT_SECONDS", 0.01,
        ), self.assertRaisesRegex(
            BodySwayCaptureServerLeaseError,
            "permanent shutdown failure.*thread_alive=false",
        ):
            lease.close()
        self.assertFalse(lease.thread_alive)
        self.assertTrue(server.closed)
        self.assertEqual(1, server.close_calls)
        lease.close()

    def test_permanent_failure_is_never_reported_as_cleaned(self):
        server = _NeverStopsServer()
        lease = BodySwayCaptureServerLease(server)
        lease.__enter__()
        try:
            with patch(
                "autospine_workbench.body_sway_capture_server_lease."
                "STOP_TIMEOUT_SECONDS", 0.01,
            ):
                for _attempt in range(2):
                    with self.assertRaisesRegex(
                        BodySwayCaptureServerLeaseError,
                        "thread_alive=true",
                    ):
                        lease.close()
                    self.assertTrue(lease.thread_alive)
            self.assertEqual(1, server.close_calls)
        finally:
            server.stop.set()
            lease._thread.join(1)
        self.assertFalse(lease.thread_alive)


if __name__ == "__main__":
    unittest.main()
