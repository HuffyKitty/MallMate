$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
Push-Location (Join-Path $projectRoot 'backend')
try {
    # 每次启动先应用版本化迁移，确保旧 SQLite 和 PostgreSQL 都拥有最新表结构。
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m uvicorn app.main:app --reload --port 18080
} finally {
    Pop-Location
}

