$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
Push-Location (Join-Path $projectRoot 'backend')
try {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m uvicorn app.main:app --reload --port 18080
} finally {
    Pop-Location
}

