$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:npm_config_cache = Join-Path $projectRoot '.cache\npm'
$env:APPDATA = Join-Path $projectRoot '.cache\appdata'
$env:LOCALAPPDATA = Join-Path $projectRoot '.cache\localappdata'
Push-Location (Join-Path $projectRoot 'frontend')
try {
    npm run dev
} finally {
    Pop-Location
}

