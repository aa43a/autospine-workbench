[CmdletBinding()]
param(
    [string]$PythonExe,
    [string]$ListenHost = "127.0.0.1",
    [ValidateRange(0, 65535)]
    [int]$Port = 8765,
    [string]$WorkspaceRoot,
    [string]$StateRoot,
    [string]$WebRoot
)

$ErrorActionPreference = "Stop"

if (-not $WorkspaceRoot) {
    $WorkspaceRoot = Split-Path -Parent $PSScriptRoot
}
if (-not $StateRoot) {
    $StateRoot = Join-Path $PSScriptRoot "workspace"
}
if (-not $WebRoot) {
    $WebRoot = Join-Path $PSScriptRoot "web"
}

$pythonCommand = $null
$pythonPrefixArgs = @()

if ($PythonExe) {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Python executable does not exist: $PythonExe"
    }
    $pythonCommand = (Resolve-Path -LiteralPath $PythonExe).Path
}

if (-not $pythonCommand -and $env:AUTOSPINE_PYTHON) {
    if (-not (Test-Path -LiteralPath $env:AUTOSPINE_PYTHON -PathType Leaf)) {
        throw "AUTOSPINE_PYTHON does not point to a file: $env:AUTOSPINE_PYTHON"
    }
    $pythonCommand = (Resolve-Path -LiteralPath $env:AUTOSPINE_PYTHON).Path
}

if (-not $pythonCommand) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
        $pythonCommand = $bundledPython
    }
}

if (-not $pythonCommand) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) {
        $pythonCommand = $systemPython.Source
    }
}

if (-not $pythonCommand) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        $pythonCommand = $pythonLauncher.Source
        $pythonPrefixArgs = @("-3")
    }
}

if (-not $pythonCommand) {
    throw "Python 3.11+ was not found. Pass -PythonExe or set AUTOSPINE_PYTHON."
}

$sourceRoot = Join-Path $PSScriptRoot "src"
$previousPythonPath = $env:PYTHONPATH
$pathSeparator = [IO.Path]::PathSeparator
$env:PYTHONPATH = if ($previousPythonPath) {
    "$sourceRoot$pathSeparator$previousPythonPath"
} else {
    $sourceRoot
}

try {
    & $pythonCommand @pythonPrefixArgs -m autospine_workbench serve `
        --host $ListenHost `
        --port $Port `
        --workspace $WorkspaceRoot `
        --state-root $StateRoot `
        --web-root $WebRoot
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
