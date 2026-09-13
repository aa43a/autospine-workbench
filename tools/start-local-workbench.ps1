param(
    [int]$Port = 8918,
    [string]$Python = 'python',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Invalid port' }
$repoRoot = Split-Path $PSScriptRoot -Parent
$assetRoot = Split-Path $repoRoot -Parent
$posePython = Join-Path $assetRoot 'tmp/pose-runner-env/Scripts/python.exe'
$poseModel = Join-Path $assetRoot 'tmp/pose-models/dwpose/dw-ll_ucoco_384.onnx'
foreach ($required in @($posePython, $poseModel)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing configured pose dependency: $required"
    }
}
$env:AUTOSPINE_POSE_PYTHON = $posePython
$env:AUTOSPINE_POSE_MODEL = $poseModel
$env:PYTHONPATH = Join-Path $repoRoot 'src'
& $Python -c 'from autospine_workbench.automation.input_preparation_runner import PoseRunnerConfig; s=PoseRunnerConfig.from_environment().public_status(); print(s); raise SystemExit(0 if s["status"] == "ready" else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Pose runner verification failed; service not started' }
if ($CheckOnly) { return }
Push-Location $repoRoot
try {
    & $Python -m autospine_workbench serve --host 127.0.0.1 --port $Port --workspace $assetRoot --state-root workspace --web-root web
    if ($LASTEXITCODE -ne 0) { throw "Workbench exited with code $LASTEXITCODE" }
} finally { Pop-Location }
