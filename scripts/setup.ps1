param(
    [string]$PythonExe = 'F:\python\python3.11.4\python.exe'
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
$env:npm_config_cache = Join-Path $projectRoot '.cache\npm'
$env:APPDATA = Join-Path $projectRoot '.cache\appdata'
$env:LOCALAPPDATA = Join-Path $projectRoot '.cache\localappdata'

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Push-Location $projectRoot
try {
    & $venvPython -m pip install -e .\backend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Set-Location (Join-Path $projectRoot 'frontend')
    npm ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host 'MallMate 本地依赖已安装到 F 盘项目目录。'

