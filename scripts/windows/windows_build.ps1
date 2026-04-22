$ErrorActionPreference = "Stop"

trap {
    Write-Error "Build failed in $($MyInvocation.ScriptName) at line $($_.InvocationInfo.ScriptLineNumber)"
    exit 1
}

Write-Host "Delete system python from host machine before compiling, otherwise linking will not work"

function Test-CommandExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

# Install Chocolatey if needed
$chocoBin = Join-Path $env:ProgramData "chocolatey\bin"
if (-not (Test-Path $chocoBin)) {
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -NoProfile `
        -InputFormat None `
        -ExecutionPolicy Bypass `
        -Command "[System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"

    $env:Path += ";$chocoBin"
}

if (-not (Test-Path "$env:ProgramFiles\Git")) {
    choco install -y git
}

if (-not (Test-Path "$env:ProgramFiles\CMake")) {
    choco install -y cmake --installargs 'ADD_CMAKE_TO_PATH=System' --apply-install-arguments-to-dependencies
}

if (-not (Test-Path "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools")) {
    winget install Microsoft.VisualStudio.2022.BuildTools --silent --override "--wait --quiet --add ProductLang En-us --add Microsoft.VisualStudio.Workload.VCTools;includeRecommended"
}

# Resolve script and project directories
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_DIR = (Resolve-Path (Join-Path $SCRIPT_DIR "..\..")).Path

if (-not (Test-Path $PROJECT_DIR -PathType Container)) {
    throw "Project directory $PROJECT_DIR does not exist"
}

$pyproject = Join-Path $PROJECT_DIR "pyproject.toml"
$setupPy   = Join-Path $PROJECT_DIR "setup.py"

if (-not (Test-Path $pyproject) -and -not (Test-Path $setupPy)) {
    throw "Invalid Python project directory, did not find either pyproject.toml or setup.py in $PROJECT_DIR"
}

Write-Host "Project Directory: $PROJECT_DIR"

$BASE = (Get-Location).Path
Write-Host "Base Directory: $BASE"

Set-Location $PROJECT_DIR

if (Test-Path "$BASE\dist") {
    Remove-Item "$BASE\dist\*" -Force -ErrorAction SilentlyContinue
}
if (Test-Path "$BASE\wheelhouse") {
    Remove-Item "$BASE\wheelhouse\*" -Force -ErrorAction SilentlyContinue
}

& (Join-Path $PROJECT_DIR "scripts\windows\python\install.ps1")

# set $pyList = @(310, 311, 312, 313, 314)
$pyList = @(313)

foreach ($v in $pyList) {
    Set-Location $BASE

    $pythonExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
    $venvDir   = Join-Path $BASE "py$v"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    & $pythonExe -m venv $venvDir
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install build delvewheel

    Set-Location $PROJECT_DIR
    & $venvPython -m build --outdir "$BASE\dist"

    & $venvPython -m delvewheel repair "$BASE\dist\kankakee*cp$v-cp$v-*.whl" --wheel-dir "$BASE\wheelhouse"
    $fixedWheels = Get-ChildItem "$BASE\wheelhouse\kankakee*cp$v-cp$v-*.whl" -ErrorAction SilentlyContinue
    foreach ($wheel in $fixedWheels) {
        & $venvPython -m pip install --force-reinstall $wheel.FullName
    }

    Set-Location $BASE
}