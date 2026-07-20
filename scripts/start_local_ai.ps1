param(
    [int]$Port = 8080,
    [int]$ContextSize = 4096
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelPath = Join-Path $projectRoot "models\Qwen3-1.7B-Q4_K_M.gguf"
$logDirectory = Join-Path $projectRoot "data\ai_logs"

if (-not (Test-Path -LiteralPath $modelPath)) {
    throw "로컬 AI 모델을 찾을 수 없습니다: $modelPath"
}

$serverCommand = Get-Command llama-server.exe -ErrorAction SilentlyContinue
if ($serverCommand) {
    $serverPath = $serverCommand.Source
} else {
    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $serverPath = Get-ChildItem -LiteralPath $packageRoot -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*ggml.llamacpp*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $serverPath) {
    throw "llama-server.exe를 찾을 수 없습니다. winget install llama.cpp 명령으로 먼저 설치하세요."
}

$existingServer = Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "--port\s+$Port(?:\s|$)" } |
    Select-Object -First 1
if ($existingServer) {
    Write-Output "KBOFM 로컬 AI 서버가 이미 실행 중입니다. PID=$($existingServer.ProcessId)"
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$stdoutPath = Join-Path $logDirectory "local_ai.stdout.log"
$stderrPath = Join-Path $logDirectory "local_ai.stderr.log"
$pidPath = Join-Path $logDirectory "local_ai.pid"
$arguments = @(
    "-m", $modelPath,
    "--alias", "kbofm-local",
    "--host", "127.0.0.1",
    "--port", $Port,
    "--ctx-size", $ContextSize,
    "--parallel", "1",
    "--n-gpu-layers", "99"
)

$startParameters = @{
    FilePath = $serverPath
    ArgumentList = $arguments
    WorkingDirectory = $projectRoot
    WindowStyle = "Hidden"
    RedirectStandardOutput = $stdoutPath
    RedirectStandardError = $stderrPath
    PassThru = $true
}
$process = Start-Process @startParameters
Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ascii

Write-Output "KBOFM 로컬 AI 서버를 시작했습니다. PID=$($process.Id), http://127.0.0.1:$Port/v1"
