@echo off
echo Delete system python from host machine before compiling, otherwise linking will not work


if not exist "%ALLUSERSPROFILE%\chocolatey\bin\" (
    @"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
)
if not exist "%ProgramFiles%\Git\" (
    choco install -y git
)
if not exist "%ProgramFiles%\CMake\" (
    choco install -y cmake --installargs 'ADD_CMAKE_TO_PATH=System' --apply-install-arguments-to-dependencies
)
if not exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\" (
    winget install Microsoft.VisualStudio.2022.BuildTools --silent --override "--wait --quiet --add ProductLang En-us --add Microsoft.VisualStudio.Workload.VCTools;includeRecommended"
)

cd %HOMEPATH%\kankakee

call scripts\windows\python\install

set list=(310 311 312 313 314)
for %%v in %list% do (
    cd %HOMEPATH%
    %LOCALAPPDATA%\Programs\Python\Python%%v\python -m venv py%%v
    call py%%v\Scripts\activate
    python.exe -m pip install --upgrade pip
    pip install build delvewheel
    cd kankakee
    python -m build
    delvewheel repair dist\*cp%%v-cp%%v-*.whl
    call deactivate
)
