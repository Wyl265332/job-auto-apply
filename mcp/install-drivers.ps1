# 一键安装 bsk 驱动（Windows / PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File mcp\install-drivers.ps1
#
# chrome-devtools 是 npm 包，不需要下载，改 MCP 配置即可（见 mcp\README.md）。
# 这个脚本只负责把 bsk.exe 放到 PATH 里，并做一次体检。

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $here "bsk\bsk.exe"
$dest = Join-Path $env:USERPROFILE ".local\bin"

if (-not (Test-Path $src)) {
    Write-Host "[跳过] 没找到 $src —— 你下载的是纯 skill 包（不含驱动二进制）。" -ForegroundColor Yellow
    Write-Host "        要 bsk 的话去官方渠道下载，或直接用 chrome-devtools（推荐）。" -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
Copy-Item $src (Join-Path $dest "bsk.exe") -Force
Write-Host "[OK] bsk.exe -> $dest\bsk.exe" -ForegroundColor Green

# 检查 dest 是否已在 PATH
$inPath = ($env:PATH -split ";") -contains $dest
if (-not $inPath) {
    Write-Host "[提示] $dest 还不在 PATH 里。要永久生效请执行：" -ForegroundColor Yellow
    Write-Host "       [Environment]::SetEnvironmentVariable('PATH', `$env:PATH + ';$dest', 'User')"
    $env:PATH += ";$dest"
}

Write-Host ""
Write-Host "体检：" -ForegroundColor Cyan
& (Join-Path $dest "bsk.exe") --version

Write-Host ""
Write-Host "下一步（必须手动）：" -ForegroundColor Cyan
Write-Host "  1. 在 Chrome / Edge 里安装 bsk 的浏览器扩展并开启连接"
Write-Host "  2. 回到 skill 目录跑：python scripts\workflow.py doctor"
