# 用途：检查前端依赖，启动本机 Vite 开发服务；无参数，不构建发布产物。
# 端口被占用时直接报错，避免另起端口导致访问到错误的开发实例。
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
    # 无论开发服务如何结束，都恢复调用者的工作目录。
    Pop-Location
}
