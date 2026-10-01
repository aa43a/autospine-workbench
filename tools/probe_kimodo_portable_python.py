"""Import/driver/small-tensor probe inside the staged private Python only.

No model is loaded and no motion is generated. JSON describes this machine;
successful CUDA here is not a promise for a different GPU or driver.
"""
import importlib
import contextlib
import io
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import sys

MODULES = (
    "accelerate", "annotated_doc", "annotated_types", "antlr4", "anyio", "av",
    "boto3", "botocore", "brotli", "bvhio", "certifi", "click", "colorama",
    "dateutil", "einops", "fastapi", "filelock", "fsspec", "gradio_client",
    "groovy", "h11", "hf_gradio", "hf_xet", "httpcore", "httpx", "huggingface_hub",
    "hydra", "idna", "jinja2", "jmespath", "kimodo", "markdown_it", "markupsafe",
    "mdurl", "mpmath", "networkx", "numpy", "omegaconf", "orjson", "packaging",
    "pandas", "peft", "PIL", "pkg_resources", "psutil", "pydantic", "pydantic_core",
    "pydub", "glm", "pygments", "python_multipart", "pytz", "yaml", "regex", "rich",
    "s3transfer", "safehttpx", "safetensors", "scenepic", "scipy", "semantic_version",
    "setuptools", "shellingham", "six", "SpatialTransform", "starlette", "sympy",
    "tokenizers", "tomlkit", "torch", "tqdm", "transformers", "trimesh", "typer",
    "typing_extensions", "typing_inspection", "tzdata", "urllib3", "uvicorn",
    "kimodo.scripts.generate", "kimodo.model.llm2vec.llm2vec",
)


def main():
    expected_root = Path(sys.argv[1]).resolve()
    if Path(sys.executable).resolve() != expected_root / ".venv/Scripts/python.exe":
        raise SystemExit("Probe must use the staged private interpreter")
    results = {"schema": "autospine.kimodo-portable-python-probe/v1", "runtime_root": str(expected_root),
               "version": sys.version, "executable": sys.executable, "prefix": sys.prefix,
               "base_prefix": sys.base_prefix, "sys_path": sys.path,
               "isolated": bool(sys.flags.isolated), "ignore_environment": bool(sys.flags.ignore_environment),
               "no_user_site": bool(sys.flags.no_user_site), "dont_write_bytecode": sys.dont_write_bytecode,
               "utf8_mode": sys.flags.utf8_mode, "model_load_performed": False,
               "source_startup_guard_verified": getattr(sys, "_kimodo_source_guard_verified", False),
               "generation_performed": False, "runtime_ready": False,
               "environment_challenges": {name: os.environ.get(name) for name in
                                          ("PATH", "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE")},
               "imports": [], "import_messages": [], "dependency_errors": [], "cuda": {"available": False}}
    results["optional_imports_not_run"] = {"gradio": "Demo import creates .pyi/hash_seed files inside its installation; CLI generation does not import this module. All original code and metadata remain inventoried."}
    for name in MODULES:
        try:
            messages = io.StringIO()
            with contextlib.redirect_stdout(messages):
                module = importlib.import_module(name)
            if messages.getvalue():
                results["import_messages"].append({"module": name, "message": messages.getvalue()})
            origin = getattr(module, "__file__", None)
            if origin and not Path(origin).resolve().is_relative_to(expected_root):
                raise ValueError("Imported outside private runtime: " + origin)
            results["imports"].append({"name": name, "ok": True, "origin": origin})
        except Exception as exc:
            results["imports"].append({"name": name, "ok": False, "error": type(exc).__name__ + ": " + str(exc)})
    try:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        installed = list(distributions(path=[str(expected_root / ".venv/Lib/site-packages")]))
        versions = {canonicalize_name(d.metadata["Name"]): d.version for d in installed}
        for dist in installed:
            for raw in dist.requires or []:
                req = Requirement(raw)
                if req.marker and not req.marker.evaluate({"extra": ""}):
                    continue
                version = versions.get(canonicalize_name(req.name))
                if version is None or (req.specifier and not req.specifier.contains(version, prereleases=True)):
                    results["dependency_errors"].append({"package": dist.metadata["Name"], "requirement": raw,
                                                         "installed_version": version})
        results["installed_versions"] = dict(sorted(versions.items()))
    except Exception as exc:
        results["dependency_errors"].append({"error": str(exc)})
    try:
        import ctypes
        driver = ctypes.WinDLL("nvcuda.dll", winmode=0x00000800)  # system driver only
        version = ctypes.c_int()
        code = driver.cuDriverGetVersion(ctypes.byref(version))
        results["cuda"]["driver_api_status"] = code
        results["cuda"]["driver_api_version"] = version.value if code == 0 else None
        import torch
        results["cuda"].update(torch_version=torch.__version__, torch_cuda_version=torch.version.cuda,
                                available=torch.cuda.is_available(), device_count=torch.cuda.device_count())
        if results["cuda"]["available"]:
            props = torch.cuda.get_device_properties(0)
            x = torch.tensor([1.0, 2.0, 3.0], device="cuda:0")
            value = float((x * x).sum().item())
            half = torch.eye(4, device="cuda:0", dtype=torch.float16)
            half_value = float((half @ half).sum().item())
            torch.cuda.synchronize()
            if value != 14.0 or half_value != 4.0:
                raise ValueError("Unexpected small CUDA tensor result")
            results["cuda"].update(device_name=props.name, compute_capability=[props.major, props.minor],
                                   total_vram_bytes=props.total_memory, small_tensor_result=value,
                                   half_matmul_result=half_value, small_tensor_probe_passed=True)
            del x, half
            torch.cuda.empty_cache()
    except Exception as exc:
        results["cuda"]["error"] = type(exc).__name__ + ": " + str(exc)
    forbidden = [n for n in sys.modules if n.startswith("__editable__") or n in ("_virtualenv", "usercustomize")]
    results["development_hooks_loaded"] = forbidden
    results["imports_ok"] = all(row["ok"] for row in results["imports"])
    results["path_isolation_ok"] = (results["isolated"] and results["ignore_environment"] and
                                     results["no_user_site"] and results["dont_write_bytecode"] and
                                     results["utf8_mode"] == 1 and not forbidden and
                                     all(p and Path(p).resolve().is_relative_to(expected_root) for p in sys.path))
    results["probe_ok"] = bool(results["imports_ok"] and results["path_isolation_ok"] and
                               results["source_startup_guard_verified"] and
                               not results["dependency_errors"] and results["cuda"].get("small_tensor_probe_passed"))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
