"""Fingerprint the static local compiler closure for Preview v2.

The closure starts at ``p10_preview_v2_service.py`` and includes only package
modules reached by static imports. Dynamically selected current-project-chain
algorithms are intentionally outside this graph: their ``algorithm_runtime``
identity is already folded into the current-chain content identity consumed by
Preview v2. Downstream candidates, decisions, manifests, and artifacts remain
bound by their existing content hashes.
"""

from __future__ import annotations

import ast
import hashlib
import keyword
from pathlib import Path


_DOMAIN = b"autospine-p10-preview-v2-static-compiler-closure/v1\0"
_ENTRY_MODULE = "p10_preview_v2_service"
_MAX_MODULES = 2_048
_MAX_SOURCE_BYTES = 4 * 1024 * 1024


class P10PreviewV2CompilerInventoryError(RuntimeError):
    """Raised when the local compiler graph cannot be proven complete."""


def preview_v2_compiler_inventory_sha256(
    package_root: Path,
    entry_module: str = _ENTRY_MODULE,
) -> str:
    """Return a path-independent digest of the entry's local import closure."""

    root = _root(package_root)
    package = root.name
    _require_name(package, "package")
    entry = _qualified_entry(package, entry_module)
    pending = {package, entry}
    sources: dict[str, bytes] = {}
    visited: set[str] = set()
    while pending:
        if len(visited) + len(pending) > _MAX_MODULES:
            raise P10PreviewV2CompilerInventoryError(
                "Preview compiler module inventory is too large"
            )
        module = min(pending)
        pending.remove(module)
        if module in visited:
            continue
        relative, payload, is_package = _source(root, package, module)
        tree = _parse(payload, relative)
        sources[relative] = payload
        visited.add(module)
        for dependency in _dependencies(tree, module, package, is_package):
            if dependency not in visited:
                pending.add(dependency)
    digest = hashlib.sha256(_DOMAIN)
    for relative in sorted(sources):
        path_bytes = relative.encode("utf-8")
        payload = sources[relative]
        digest.update(len(path_bytes).to_bytes(4, "big"))
        digest.update(path_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P10PreviewV2CompilerInventoryError(
            "Preview compiler package root is unavailable"
        ) from exc
    if not root.is_dir():
        raise P10PreviewV2CompilerInventoryError(
            "Preview compiler package root is not a directory"
        )
    return root


def _qualified_entry(package: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise P10PreviewV2CompilerInventoryError(
            "Preview compiler entry module is invalid"
        )
    for part in value.split("."):
        _require_name(part, "entry module")
    return f"{package}.{value}"


def _require_name(value: str, label: str) -> None:
    if not value.isidentifier() or keyword.iskeyword(value):
        raise P10PreviewV2CompilerInventoryError(
            f"Preview compiler {label} is invalid"
        )


def _source(root: Path, package: str, module: str):
    parts = module.split(".")
    if not parts or parts[0] != package:
        raise P10PreviewV2CompilerInventoryError(
            "Preview compiler dependency escaped its package"
        )
    for part in parts:
        _require_name(part, "dependency")
    stem = root.joinpath(*parts[1:]) if len(parts) > 1 else root
    choices = [root / "__init__.py"] if module == package else [
        stem.with_suffix(".py"), stem / "__init__.py",
    ]
    existing = [path for path in choices if path.is_file()]
    if len(existing) != 1:
        raise P10PreviewV2CompilerInventoryError(
            f"Preview compiler dependency is missing or ambiguous: {module}"
        )
    path = existing[0]
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        payload = resolved.read_bytes()
    except (OSError, RuntimeError, ValueError) as exc:
        raise P10PreviewV2CompilerInventoryError(
            f"Preview compiler dependency is unsafe: {module}"
        ) from exc
    if not payload or len(payload) > _MAX_SOURCE_BYTES:
        raise P10PreviewV2CompilerInventoryError(
            f"Preview compiler source size is invalid: {module}"
        )
    return path.relative_to(root).as_posix(), payload, path.name == "__init__.py"


def _parse(payload: bytes, relative: str) -> ast.AST:
    try:
        return ast.parse(payload, filename=relative)
    except (SyntaxError, UnicodeError, ValueError) as exc:
        raise P10PreviewV2CompilerInventoryError(
            f"Preview compiler source is invalid: {relative}"
        ) from exc


def _dependencies(tree, module: str, package: str, is_package: bool):
    result: set[str] = set()
    current_package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _add_absolute(result, alias.name, package)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _relative_base(current_package, node.level, package)
                if node.module:
                    _add_absolute(result, f"{base}.{node.module}", package)
                else:
                    for alias in node.names:
                        if alias.name == "*":
                            raise P10PreviewV2CompilerInventoryError(
                                "Preview compiler relative wildcard is unknown"
                            )
                        _add_absolute(
                            result, f"{base}.{alias.name}", package,
                        )
            elif node.module:
                _add_absolute(result, node.module, package)
    return result


def _relative_base(current: str, level: int, package: str) -> str:
    parts = current.split(".")
    drop = level - 1
    if drop >= len(parts) or parts[0] != package:
        raise P10PreviewV2CompilerInventoryError(
            "Preview compiler relative import escaped its package"
        )
    return ".".join(parts[:len(parts) - drop])


def _add_absolute(result: set[str], module: str, package: str) -> None:
    parts = module.split(".")
    if not parts or parts[0] != package:
        return
    for part in parts:
        _require_name(part, "import")
    for length in range(1, len(parts) + 1):
        result.add(".".join(parts[:length]))


__all__ = [
    "P10PreviewV2CompilerInventoryError",
    "preview_v2_compiler_inventory_sha256",
]
