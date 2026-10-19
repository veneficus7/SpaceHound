# Build SpaceHound.exe:  .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt

Write-Host "Running tests..."
& .venv\Scripts\python.exe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "Building..."
& .venv\Scripts\pyinstaller.exe spacehound.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

$exe = Get-Item "dist\SpaceHound.exe"
Write-Host ("Done: {0} ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB))
