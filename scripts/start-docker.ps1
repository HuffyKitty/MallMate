param(
    [string]$RuntimeRoot = 'E:\Develop\DockerRuntime\LocalAppData'
)

$dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
if (-not (Test-Path -LiteralPath $dockerDesktop)) {
    Write-Error '未找到 Docker Desktop，请先安装 Docker Desktop。'
    exit 1
}

if (Get-Process -Name 'com.docker.backend' -ErrorAction SilentlyContinue) {
    Write-Host 'Docker Desktop 后台已经在运行。'
    exit 0
}

# Docker Desktop 4.61 在当前 Windows 环境留下了无法删除的 C 盘 Unix Socket。
# 仅给 Docker 子进程设置 E 盘运行时目录，不修改系统级 LOCALAPPDATA，也不移动镜像数据。
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $RuntimeRoot
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
}

Write-Host "Docker Desktop 已启动，临时运行文件位于 $RuntimeRoot。"
