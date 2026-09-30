"""Crash-released, state-wide engine ownership and bound endpoint discovery."""
from copy import deepcopy
from ipaddress import ip_address
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
from uuid import uuid4

from .automation.storage_io import canonical_bytes, directory
from .motion_instance_v3_staging_cleanup import is_alias
from .safe_input_files import read_real_file, strict_json_object
from .spine42_v3_bundle_files import existing_exact_child
from .staging_file import create_staging_file


SCHEMA = 'autospine.engine-session/v1'
SESSION_DIRECTORY = 'engine-session-v1'
ENDPOINT_FILE = 'endpoint.json'
SESSION_HEADER = 'X-Autospine-Engine-Session'
SESSION_MISMATCH_HEADER = 'X-Autospine-Engine-Session-Mismatch'


def validate_request_session(handler):
    """Reject a stale Studio connection before any read or mutation dispatch.

    Existing browser clients do not send this optional desktop session header.
    """
    supplied = handler.headers.get_all(SESSION_HEADER, [])
    if not supplied:
        return True
    current = getattr(handler.server, 'engine_session', None)
    if len(supplied) == 1 and isinstance(current, dict) and supplied[0] == current.get('nonce'):
        return True
    handler._send_bytes(409, canonical_bytes(dict(error='engine_session_changed',
        message='Engine session changed; refresh before retrying this operation.')),
        'application/json; charset=utf-8', extra_headers={SESSION_MISMATCH_HEADER: '1'})
    return False


class EngineSessionLease:
    """One mutable project state may have exactly one service owner."""

    def __init__(self, state_root, workspace_root):
        self.state_root = Path(state_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self.root = directory(self.state_root / SESSION_DIRECTORY, create=True)
        self._descriptor = None
        self._identity = None
        self._acquire()

    def _acquire(self):
        path = self.root / 'owner.lock'
        descriptor = None
        try:
            existing_exact_child(self.root, path.name)
            flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            descriptor = os.open(path, flags, 0o600)
            os.set_inheritable(descriptor, False)
            opened, linked = os.fstat(descriptor), path.lstat()
            if (is_alias(path) or not stat.S_ISREG(linked.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)):
                raise OSError('Workbench engine ownership file is invalid.')
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b'\0')
                os.fsync(descriptor)
            self._descriptor = descriptor
        except (OSError, RuntimeError, ValueError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise OSError('Workbench state is already owned or ownership is unavailable.') from exc

    def publish(self, origin):
        """Publish only after a listener has successfully bound its actual port."""
        if self._descriptor is None:
            raise OSError('Workbench engine ownership is closed.')
        parsed = urlsplit(origin)
        if (parsed.scheme != 'http' or not ip_address(parsed.hostname).is_loopback
                or not parsed.port or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('Workbench endpoint must be a bound loopback address.')
        value = dict(schema=SCHEMA, nonce=uuid4().hex, pid=os.getpid(),
                     state_root=str(self.state_root), workspace_root=str(self.workspace_root),
                     origin=origin)
        endpoint = self.root / ENDPOINT_FILE
        if existing_exact_child(self.root, ENDPOINT_FILE) is not None:
            read_real_file(endpoint, 4096, 'engine endpoint')
        descriptor, temporary = create_staging_file(self.root, prefix='endpoint-')
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, endpoint)
            if strict_json_object(read_real_file(endpoint, 4096, 'engine endpoint'), 'engine endpoint') != value:
                raise OSError('Workbench endpoint publication failed exact readback.')
        finally:
            Path(temporary).unlink(missing_ok=True)
        self._identity = value
        return deepcopy(value)

    def close(self):
        descriptor = self._descriptor
        if descriptor is None:
            return
        try:
            endpoint = self.root / ENDPOINT_FILE
            if self._identity is not None and endpoint.exists():
                current = strict_json_object(read_real_file(endpoint, 4096, 'engine endpoint'), 'engine endpoint')
                if current == self._identity:
                    endpoint.unlink()
        finally:
            # Closing the non-inheritable descriptor releases the OS lease even
            # after abnormal termination; no stale PID is execution authority.
            self._descriptor = None
            self._identity = None
            os.close(descriptor)
