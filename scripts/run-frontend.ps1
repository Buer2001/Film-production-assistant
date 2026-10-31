$ErrorActionPreference = 'Stop'
$frontendRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules/.bin/vite.cmd'))) {
    throw '缺少前端依赖，请先在 frontend 目录执行 npm ci。'
}
Push-Location -LiteralPath $frontendRoot
try {
    & npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
    if ($LASTEXITCODE -ne 0) { throw "前端启动失败，退出码：$LASTEXITCODE" }
} finally {
    Pop-Location
}
