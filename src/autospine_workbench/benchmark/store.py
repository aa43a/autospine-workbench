"""Immutable benchmark manifests; publication never replaces an old address."""
from pathlib import Path

from ..automation.storage_io import directory, publish_document, read_document
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from ..spine42_v3_bundle_files import existing_exact_child
from .validation import BenchmarkError, require_digest, validate_benchmark_manifest


class BenchmarkManifestStore:
    def __init__(self, state_root):
        self.state_root = Path(state_root)
        self.root = self.state_root / "benchmarks"

    def _folder(self, dataset_id, *, create=False):
        require_safe_token(dataset_id, "Dataset id")
        current = directory(self.state_root, create=create)
        for name in ("benchmarks", dataset_id, "manifests"):
            found = existing_exact_child(current, name)
            if found is None and not create:
                raise BenchmarkError("benchmark_manifest_not_found")
            current = directory(current / name, create=create)
        return current

    def publish(self, document):
        """Return its canonical SHA; even a frozen version is append-only."""
        try:
            manifest = validate_benchmark_manifest(document)
            digest = canonical_sha256(manifest)
            folder = self._folder(manifest["dataset_id"], create=True)
            publish_document(folder / f"{digest}.json", manifest, staging=folder.parent / "staging")
            if self.load(manifest["dataset_id"], digest) != manifest:
                raise BenchmarkError("benchmark_manifest_identity_mismatch")
            return digest
        except BenchmarkError:
            raise
        except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
            raise BenchmarkError("benchmark_store_invalid") from exc

    def load(self, dataset_id, sha256):
        try:
            require_digest(sha256)
            folder = self._folder(dataset_id)
            path = existing_exact_child(folder, f"{sha256}.json")
            if path is None:
                raise BenchmarkError("benchmark_manifest_not_found")
            if path.lstat().st_nlink != 1:
                raise BenchmarkError("benchmark_store_alias")
            manifest = validate_benchmark_manifest(read_document(path))
            if manifest["dataset_id"] != dataset_id or canonical_sha256(manifest) != sha256:
                raise BenchmarkError("benchmark_manifest_identity_mismatch")
            return manifest
        except BenchmarkError:
            raise
        except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
            raise BenchmarkError("benchmark_store_invalid") from exc
