param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '缺少虚拟环境，请先在 project 目录执行 python -m venv .venv，并安装 requirements.txt。'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    throw '缺少 .env，请复制 .env.example 为 .env 后填写配置。'
}
# 固定工作目录，让 SQLite 路径和模型提示词加载不受启动位置影响。
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m uvicorn backend.main:app --reload --host 127.0.0.1 --port $Port --env-file .env
    if ($LASTEXITCODE -ne 0) { throw "后端启动失败，退出码：$LASTEXITCODE" }
} finally {
    Pop-Location
}
