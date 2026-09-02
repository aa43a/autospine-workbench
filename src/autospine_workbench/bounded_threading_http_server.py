"""Internal bounded-concurrency HTTP transport."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import socket
import threading
import time


_MAX_CONCURRENT_REQUESTS = 16
_MAX_OVERLOAD_DRAIN_BYTES = 64 * 1024
_OVERLOAD_RESPONSE = (
    b"HTTP/1.1 503 Service Unavailable\r\n"
    b"Connection: close\r\n"
    b"Content-Length: 0\r\n"
    b"Cache-Control: no-store\r\n\r\n"
)


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Start no more than 16 request threads."""

    def __init__(self, *args, **kwargs) -> None:
        self._request_slots = threading.BoundedSemaphore(
            _MAX_CONCURRENT_REQUESTS
        )
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address) -> None:
        if not self._request_slots.acquire(blocking=False):
            self._reject_overload(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def _reject_overload(self, request) -> None:
        deadline = time.monotonic() + 0.25
        try:
            request.settimeout(0.25)
            request.sendall(_OVERLOAD_RESPONSE)
            request.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        remaining = _MAX_OVERLOAD_DRAIN_BYTES
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                request.settimeout(timeout)
                chunk = request.recv(min(remaining, 4096))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass
        finally:
            self.shutdown_request(request)


__all__: list[str] = []
