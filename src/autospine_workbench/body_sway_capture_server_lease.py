"""Fail-closed lifecycle wrapper for the loopback capture server."""

from __future__ import annotations

import threading
from typing import Any


START_TIMEOUT_SECONDS = 5.0
STOP_TIMEOUT_SECONDS = 5.0


class BodySwayCaptureServerLeaseError(RuntimeError):
    """Raised when the capture server cannot start, stay healthy, or stop."""


class BodySwayCaptureServerLease:
    """Own one non-daemon server thread for the entire capture transaction."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._started = threading.Event()
        self._failed = threading.Event()
        self._serve_error: BaseException | None = None
        self._stopping = False
        self._thread_stopped = False
        self._socket_closed = False
        self._closed = False
        self._thread = threading.Thread(
            target=self._serve,
            name="autospine-body-sway-capture-server",
            daemon=False,
        )

    @property
    def is_daemon(self) -> bool:
        return self._thread.daemon

    @property
    def thread_alive(self) -> bool:
        """Expose the exact cleanup state without treating failure as closed."""

        return self._thread.is_alive()

    def __enter__(self) -> BodySwayCaptureServerLease:
        try:
            self._thread.start()
        except (OSError, RuntimeError) as exc:
            self._stopping = True
            try:
                self.close()
            except BodySwayCaptureServerLeaseError as cleanup_exc:
                self._retry_close(cleanup_exc)
                exc.add_note(f"Server cleanup also failed: {cleanup_exc}")
            raise BodySwayCaptureServerLeaseError(
                f"Runtime capture server thread could not start: {exc}"
            ) from exc
        try:
            if not self._started.wait(START_TIMEOUT_SECONDS):
                raise BodySwayCaptureServerLeaseError(
                    "Runtime capture server did not start"
                )
            self.require_healthy()
            return self
        except BodySwayCaptureServerLeaseError as exc:
            try:
                self.close()
            except BodySwayCaptureServerLeaseError as cleanup_exc:
                self._retry_close(cleanup_exc)
                exc.add_note(f"Server cleanup also failed: {cleanup_exc}")
            raise

    def __exit__(self, kind, value, traceback) -> bool:
        try:
            self.close()
        except BodySwayCaptureServerLeaseError as exc:
            self._retry_close(exc)
            if value is None:
                raise
            if hasattr(value, "add_note"):
                value.add_note(f"Capture server cleanup also failed: {exc}")
        return False

    def require_healthy(self) -> None:
        if self._failed.is_set():
            raise BodySwayCaptureServerLeaseError(
                f"Runtime capture server failed: {self._serve_error}"
            ) from self._serve_error
        if self._started.is_set() and not self._stopping \
                and not self._thread.is_alive():
            raise BodySwayCaptureServerLeaseError(
                "Runtime capture server stopped unexpectedly"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._stopping = True
        cleanup_errors: list[BaseException] = []
        if self._thread.ident is None:
            self._thread_stopped = True
        elif not self._thread_stopped:
            self._request_shutdown(cleanup_errors)
            self._join_server_thread(cleanup_errors)
        if self.thread_alive and not self._socket_closed:
            self._close_socket(cleanup_errors)
            self._join_server_thread(cleanup_errors)
        if not self.thread_alive:
            self._thread_stopped = True
        if self._thread_stopped and not self._socket_closed:
            self._close_socket(cleanup_errors)
        self._closed = self._thread_stopped and self._socket_closed
        if not self._closed and not cleanup_errors:
            cleanup_errors.append(RuntimeError("server cleanup is incomplete"))
        if cleanup_errors:
            _raise_cleanup_errors(
                cleanup_errors,
                thread_alive=self.thread_alive,
                socket_closed=self._socket_closed,
            )
        if self._closed and self._failed.is_set():
            raise BodySwayCaptureServerLeaseError(
                f"Runtime capture server failed: {self._serve_error}"
            ) from self._serve_error

    def _request_shutdown(self, errors: list[BaseException]) -> None:
        if not self.thread_alive:
            return
        try:
            # BaseServer.shutdown must run outside serve_forever's thread. The
            # lease owner is that distinct caller; no helper thread is hidden.
            self._server.shutdown()
        except BaseException as exc:
            errors.append(exc)

    def _join_server_thread(self, errors: list[BaseException]) -> None:
        if not self.thread_alive:
            self._thread_stopped = True
            return
        try:
            self._thread.join(STOP_TIMEOUT_SECONDS)
        except BaseException as exc:
            errors.append(exc)
        if self.thread_alive:
            errors.append(RuntimeError("server thread did not stop"))
        else:
            self._thread_stopped = True

    def _close_socket(self, errors: list[BaseException]) -> None:
        if self._socket_closed:
            return
        try:
            self._server.server_close()
        except BaseException as exc:
            errors.append(exc)
        else:
            self._socket_closed = True

    def _retry_close(
        self, first_error: BodySwayCaptureServerLeaseError,
    ) -> None:
        try:
            self.close()
        except BodySwayCaptureServerLeaseError as retry_error:
            first_error.add_note(
                f"Server cleanup retry also failed: {retry_error}"
            )

    def _serve(self) -> None:
        self._started.set()
        try:
            self._server.serve_forever(poll_interval=0.05)
        except BaseException as exc:
            self._serve_error = exc
            self._failed.set()
        else:
            if not self._stopping:
                self._serve_error = RuntimeError(
                    "server loop returned unexpectedly"
                )
                self._failed.set()


def _raise_cleanup_errors(
    errors: list[BaseException],
    *,
    thread_alive: bool,
    socket_closed: bool,
) -> None:
    primary = errors[0]
    for secondary in errors[1:]:
        primary.add_note(f"Additional server cleanup failure: {secondary}")
    raise BodySwayCaptureServerLeaseError(
        "Runtime capture server could not be stopped: "
        f"{primary}; thread_alive={str(thread_alive).lower()}; "
        f"socket_closed={str(socket_closed).lower()}"
    ) from primary
