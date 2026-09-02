"""Bounded-concurrency tests for the shared runtime capture transport."""

from __future__ import annotations

import http.client
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.spine42_v3_runtime_capture_server_core import (  # noqa: E402
    create_spine_runtime_capture_server_core,
)


class _Collector:
    def status(self):
        return {"complete": False}

    def record_capture(self, *args, **kwargs):
        raise AssertionError("capture is outside this transport test")

    def record_error(self, *args, **kwargs):
        raise AssertionError("error report is outside this transport test")


def _server():
    server = create_spine_runtime_capture_server_core(
        "127.0.0.1", 0,
        artifact_ids=("artifact-001",),
        session_bytes={"artifact-001": b"{}"},
        static={}, collector=_Collector(), collector_error_type=ValueError,
        page_factory=lambda artifact_id: artifact_id.encode("ascii"),
    )
    server.handle_error = lambda request, client_address: None
    return server


def _start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def _slot_value(server):
    with server._request_slots._cond:
        return server._request_slots._value


def _status_request(server):
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    try:
        connection.request("GET", "/api/status")
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _recv_all(client):
    chunks = []
    while True:
        chunk = client.recv(512)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


class RuntimeCaptureServerCapacityTests(unittest.TestCase):
    def test_sixteen_slow_clients_bound_threads_then_capacity_recovers(self):
        server = _server()
        thread = _start(server)
        host, port = server.server_address[:2]
        slow = []
        try:
            for _ in range(16):
                client = socket.create_connection((host, port), timeout=2)
                client.sendall(b"GET /api/status HTTP/1.1\r\nHost: 127.0.0.1")
                slow.append(client)
            _wait_until(lambda: _slot_value(server) == 0)

            overloaded = socket.create_connection((host, port), timeout=2)
            try:
                overloaded.sendall(
                    b"GET /api/status HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
                )
                response = _recv_all(overloaded)
            finally:
                overloaded.close()
            self.assertEqual(
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Connection: close\r\nContent-Length: 0\r\n"
                b"Cache-Control: no-store\r\n\r\n",
                response,
            )

            for client in slow:
                client.close()
            slow.clear()
            _wait_until(lambda: _slot_value(server) == 16)
            self.assertEqual(200, _status_request(server))
        finally:
            for client in slow:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_thread_start_failure_releases_slot_and_closes_request(self):
        server = _server()
        accepted, client = socket.socketpair()
        try:
            with patch("threading.Thread.start", side_effect=RuntimeError(
                "synthetic start failure"
            )), self.assertRaisesRegex(RuntimeError, "synthetic"):
                server.process_request(accepted, ("127.0.0.1", 1))
            self.assertEqual(16, _slot_value(server))
            client.settimeout(1)
            self.assertEqual(b"", client.recv(1))
            thread = _start(server)
            try:
                self.assertEqual(200, _status_request(server))
            finally:
                server.shutdown()
                thread.join(2)
            self.assertFalse(thread.is_alive())
        finally:
            client.close()
            server.server_close()

    def test_shutdown_does_not_wait_for_slow_daemon_workers(self):
        server = _server()
        thread = _start(server)
        host, port = server.server_address[:2]
        clients = []
        try:
            for _ in range(4):
                client = socket.create_connection((host, port), timeout=2)
                client.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1")
                clients.append(client)
            _wait_until(lambda: _slot_value(server) == 12)
            started = time.monotonic()
            server.shutdown()
            self.assertLess(time.monotonic() - started, 2.0)
            thread.join(2)
            self.assertFalse(thread.is_alive())
        finally:
            for client in clients:
                client.close()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
