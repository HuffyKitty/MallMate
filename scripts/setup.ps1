param(
    [string]$PythonExe = 'F:\python\python3.11.4\python.exe'
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
$env:npm_config_cache = Join-Path $projectRoot '.cache\npm'
$env:APPDATA = Join-Path $projectRoot '.cache\appdata'
$env:LOCALAPPDATA = Join-Path $projectRoot '.cache\localappdata'
$backendEnv = Join-Path $projectRoot 'backend\.env'
$backendEnvExample = Join-Path $projectRoot 'backend\.env.example'

# 真实 JWT 密钥只写入被 Git 忽略的 backend/.env。重复执行不会覆盖已有配置值。
if (-not (Test-Path -LiteralPath $backendEnv)) {
    $envText = Get-Content -LiteralPath $backendEnvExample -Raw -Encoding UTF8
} else {
    $envText = Get-Content -LiteralPath $backendEnv -Raw -Encoding UTF8
    $authDefaults = @(
        'MALLMATE_AUTH_ENABLED=true',
        'MALLMATE_JWT_ALGORITHM=HS256',
        'MALLMATE_JWT_ISSUER=mallmate-api',
        'MALLMATE_JWT_AUDIENCE=mallmate-web',
        'MALLMATE_ACCESS_TOKEN_MINUTES=15',
        'MALLMATE_REFRESH_TOKEN_DAYS=7',
        'MALLMATE_REFRESH_COOKIE_NAME=mallmate_refresh',
        'MALLMATE_REFRESH_COOKIE_PATH=/api/v1/auth',
        'MALLMATE_COOKIE_SECURE=false',
        'MALLMATE_COOKIE_SAMESITE=lax'
    )
    foreach ($entry in $authDefaults) {
        $name = ($entry -split '=', 2)[0]
        if ($envText -notmatch "(?m)^$([regex]::Escape($name))=") {
            $envText += "`r`n$entry"
        }
    }
}

if ($envText -notmatch '(?m)^MALLMATE_JWT_SECRET=\S+$') {
    $secretBytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
    $jwtSecret = [Convert]::ToBase64String($secretBytes)
    if ($envText -match '(?m)^MALLMATE_JWT_SECRET=.*$') {
        $envText = $envText -replace '(?m)^MALLMATE_JWT_SECRET=.*$', "MALLMATE_JWT_SECRET=$jwtSecret"
    } else {
        $envText += "`r`nMALLMATE_JWT_SECRET=$jwtSecret"
    }
    Write-Host '已为本机生成 JWT 签名密钥。'
}
Set-Content -LiteralPath $backendEnv -Value $envText -Encoding UTF8

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Push-Location $projectRoot
try {
    & $venvPython -m pip install -e .\backend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $venvPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
    Set-Location (Join-Path $projectRoot 'frontend')
    npm ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host 'MallMate 本地依赖已安装到 F 盘项目目录。'

